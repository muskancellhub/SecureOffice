"""BUG-AUD-010 — notification_recipients_changed uses the spec field names."""

import logging
import uuid
from types import SimpleNamespace

from app.core.logging_config import SD_ID_AUDIT
from app.services.order_notification_service import OrderNotificationService


class _FakeDB:
    def commit(self):
        pass

    def refresh(self, _row):
        pass


def test_recipients_changed_uses_spec_field_names():
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    audit_logger = logging.getLogger('secureoffice.audit')
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    try:
        svc = OrderNotificationService(_FakeDB())
        svc.user_repo = SimpleNamespace(get_by_id=lambda uid: object())
        row = SimpleNamespace(
            recipient_emails_json=['old@example.com', 'keep@example.com'],
            updated_by_user_id=None,
        )
        svc.notification_repo = SimpleNamespace(get_or_create=lambda t: row)
        cu = {'user_id': str(uuid.uuid4()), 'tenant_id': str(uuid.uuid4())}
        svc.update_recipient_settings(cu, ['keep@example.com', 'new@example.com'])
    finally:
        audit_logger.removeHandler(handler)

    rec = next(r for r in records
               if getattr(r, 'msgid', None) == 'notification_recipients_changed')
    f = rec.sd[SD_ID_AUDIT]
    assert 'recipients_added' in f and 'recipients_removed' in f
    assert 'added' not in f and 'removed' not in f  # old abbreviated names gone
    assert 'new@example.com' in f['recipients_added']
    assert 'old@example.com' in f['recipients_removed']
