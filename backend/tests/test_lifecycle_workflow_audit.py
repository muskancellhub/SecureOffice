"""BUG-AUD-013 — workflow_advanced records the transition (step_completed /
new_current_step), not just the resulting state."""

import logging
import uuid
from types import SimpleNamespace

from app.core.logging_config import SD_ID_AUDIT
from app.models.lifecycle import WorkflowStatus, WorkflowStepStatus
from app.models.order import OrderStatus
from app.services.lifecycle_service import LifecycleService


class _FakeDB:
    def __init__(self, workflow):
        self._workflow = workflow

    def commit(self):
        pass

    def refresh(self, _row):
        pass

    def scalar(self, _stmt):
        return self._workflow


def test_workflow_advanced_logs_transition_fields(monkeypatch):
    steps = [
        SimpleNamespace(sequence=1, status=WorkflowStepStatus.IN_PROGRESS,
                        stage_key='validation', started_at=object(), completed_at=None),
        SimpleNamespace(sequence=2, status=WorkflowStepStatus.PENDING,
                        stage_key='fulfillment', started_at=None, completed_at=None),
    ]
    workflow = SimpleNamespace(id=uuid.uuid4(), steps=steps,
                               current_stage='validation', status=WorkflowStatus.ACTIVE)
    order = SimpleNamespace(id=uuid.uuid4(), status=OrderStatus.SUBMITTED)

    svc = LifecycleService(_FakeDB(workflow))
    svc.user_repo = SimpleNamespace(get_by_id=lambda uid: object())
    monkeypatch.setattr(svc, 'get_order_workflow', lambda cu, oid: workflow)
    monkeypatch.setattr(svc, '_get_order_for_actor', lambda cu, oid: order)

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    audit_logger = logging.getLogger('secureoffice.audit')
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    try:
        cu = {'user_id': str(uuid.uuid4()), 'tenant_id': str(uuid.uuid4()), 'role': 'ADMIN'}
        svc.advance_order_workflow(cu, str(order.id))
    finally:
        audit_logger.removeHandler(handler)

    rec = next(r for r in records if getattr(r, 'msgid', None) == 'workflow_advanced')
    f = rec.sd[SD_ID_AUDIT]
    assert f['step_completed'] == 'validation'      # what just finished
    assert f['new_current_step'] == 'fulfillment'   # what's now in progress
    assert f['current_stage'] == 'fulfillment'      # resulting state still present
