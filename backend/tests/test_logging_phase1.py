"""Phase 1 logging foundations: RFC 5424 formatter, redaction, audit logger,
request-context fields, shared IP resolver (docs/LOGGING_PLAN.md §4, §7.1)."""
import logging
import re

import pytest
from starlette.requests import Request

from app.core.exceptions import ForbiddenError
from app.core.logging_config import (
    FACILITY_AUDIT,
    NOTICE,
    RedactionFilter,
    RFC5424Formatter,
    SD_ID_AUDIT,
    _syslog_severity,
    redact,
)
from app.core.request_context import (
    RequestContext,
    common_log_fields,
    new_request_id,
    reset_request_context,
    resolve_client_ip,
    set_request_context,
)
from app.services.audit_logger import audit

logging.addLevelName(NOTICE, 'NOTICE')

# 1 TIMESTAMP HOSTNAME APP PROCID MSGID SD MSG
RFC5424_RE = re.compile(
    r'^<(\d{1,3})>1 '
    r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z) '
    r'(\S+) (secureoffice2) (\d+) (\S+) (-|\[.*\]) (.*)$'
)


def make_record(level=NOTICE, msg='role changed', msgid='user_role_changed', sd=None):
    record = logging.LogRecord(
        name='secureoffice.audit', level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )
    record.msgid = msgid
    if sd is not None:
        record.sd = sd
    return record


def make_request(headers=None, client_host='9.9.9.9'):
    scope = {
        'type': 'http',
        'method': 'GET',
        'path': '/x',
        'query_string': b'',
        'headers': [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        'client': (client_host, 1234),
    }
    return Request(scope)


class TestFormatter:
    def test_line_shape_and_pri(self):
        formatter = RFC5424Formatter(facility=FACILITY_AUDIT, include_pri=True)
        line = formatter.format(make_record(sd={SD_ID_AUDIT: {'user_id': 'u1'}}))
        m = RFC5424_RE.match(line)
        assert m, line
        # local1 (17) * 8 + notice (5) = 141 (plan §2.1)
        assert m.group(1) == '141'
        assert m.group(6) == 'user_role_changed'
        assert 'user_id="u1"' in m.group(7)

    def test_no_pri_for_syslog_handler(self):
        formatter = RFC5424Formatter(facility=FACILITY_AUDIT, include_pri=False)
        line = formatter.format(make_record())
        assert line.startswith('1 '), 'SysLogHandler prepends PRI itself'

    def test_severity_mapping(self):
        assert _syslog_severity(logging.DEBUG) == 7
        assert _syslog_severity(logging.INFO) == 6
        assert _syslog_severity(NOTICE) == 5
        assert _syslog_severity(logging.WARNING) == 4
        assert _syslog_severity(logging.ERROR) == 3
        assert _syslog_severity(logging.CRITICAL) == 2

    def test_sd_value_escaping_and_injection(self):
        formatter = RFC5424Formatter(facility=FACILITY_AUDIT, include_pri=True)
        evil = 'a"b\\c]d\ne<999>1 forged'
        line = formatter.format(make_record(sd={SD_ID_AUDIT: {'name': evil}}))
        assert '\n' not in line
        assert 'a\\"b\\\\c\\]d' in line

    def test_newlines_stripped_from_msg(self):
        formatter = RFC5424Formatter(facility=FACILITY_AUDIT, include_pri=True)
        line = formatter.format(make_record(msg='line1\nline2'))
        assert '\n' not in line

    def test_nil_sd_and_msgid(self):
        formatter = RFC5424Formatter(facility=FACILITY_AUDIT, include_pri=True)
        record = logging.LogRecord(
            name='x', level=logging.INFO, pathname=__file__, lineno=1,
            msg='plain app log', args=(), exc_info=None,
        )
        m = RFC5424_RE.match(formatter.format(record))
        assert m and m.group(6) == '-' and m.group(7) == '-'


class TestRedaction:
    def test_denylist_keys_redacted_recursively(self):
        data = {
            'email': 'a@b.com',
            'password': 'hunter2',
            'nested': {'api_key': 'k', 'Authorization': 'Bearer x', 'ok': 1},
            'items': [{'otp_code': '123456'}],
        }
        out = redact(data)
        assert out['email'] == 'a@b.com'
        assert out['password'] == '[REDACTED]'
        assert out['nested']['api_key'] == '[REDACTED]'
        assert out['nested']['Authorization'] == '[REDACTED]'
        assert out['nested']['ok'] == 1
        assert out['items'][0]['otp_code'] == '[REDACTED]'

    def test_filter_applies_to_record_sd(self):
        record = make_record(sd={SD_ID_AUDIT: {'password': 'x', 'user_id': 'u1'}})
        assert RedactionFilter().filter(record) is True
        assert record.sd[SD_ID_AUDIT]['password'] == '[REDACTED]'
        assert record.sd[SD_ID_AUDIT]['user_id'] == 'u1'


class TestAuditLogger:
    def test_emits_msgid_sd_and_default_notice(self):
        captured = []
        handler = logging.Handler()
        handler.emit = captured.append
        target = logging.getLogger('secureoffice.audit')
        target.addHandler(handler)
        target.setLevel(logging.INFO)
        target.propagate = False
        try:
            audit.log('user_login', email='a@b.com')
        finally:
            target.removeHandler(handler)
        assert len(captured) == 1
        record = captured[0]
        assert record.levelno == NOTICE
        assert record.msgid == 'user_login'
        fields = record.sd[SD_ID_AUDIT]
        assert fields['status'] == 'success'
        assert fields['email'] == 'a@b.com'
        assert fields['request_id'] == '-'  # outside a request → nil values

    def test_never_raises(self, monkeypatch):
        import app.services.audit_logger as mod
        monkeypatch.setattr(
            mod, 'common_log_fields',
            lambda: (_ for _ in ()).throw(RuntimeError('boom')),
        )
        audit.log('user_login')  # must not raise


class TestRequestContext:
    def test_common_fields_from_context(self):
        request = make_request()
        request.state.user = {'user_id': 'u1', 'tenant_id': 't1', 'role': 'ADMIN'}
        token = set_request_context(RequestContext(
            request_id='rid-1', method='GET', path='/users',
            client_ip='1.2.3.4', user_agent='pytest', request=request,
        ))
        try:
            fields = common_log_fields()
        finally:
            reset_request_context(token)
        assert fields['request_id'] == 'rid-1'
        assert fields['endpoint'] == 'GET /users'
        assert fields['user_id'] == 'u1'
        assert fields['tenant_id'] == 't1'
        assert fields['actor_role'] == 'ADMIN'

    def test_inbound_request_id_only_when_trusted(self):
        assert new_request_id('abc-123', trust_inbound=True) == 'abc-123'
        assert new_request_id('abc-123', trust_inbound=False) != 'abc-123'
        forged = new_request_id('evil] injected', trust_inbound=True)
        assert forged != 'evil] injected'  # malformed → fresh UUID

    def test_resolve_client_ip_no_proxy(self):
        request = make_request(headers={'x-forwarded-for': '6.6.6.6'})
        assert resolve_client_ip(request, 0) == '9.9.9.9'

    def test_resolve_client_ip_behind_proxy(self):
        request = make_request(headers={'x-forwarded-for': '1.1.1.1, 2.2.2.2'})
        assert resolve_client_ip(request, 1) == '2.2.2.2'
        assert resolve_client_ip(request, 2) == '1.1.1.1'


def test_forbidden_error_carries_permission():
    exc = ForbiddenError('Missing permission: users.manage', required_permission='users.manage')
    assert exc.required_permission == 'users.manage'
    assert ForbiddenError().required_permission is None
