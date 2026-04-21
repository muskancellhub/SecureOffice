import uuid
from datetime import date, datetime, timezone
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.models.lifecycle import (
    Asset,
    AssetStatus,
    Contract,
    ContractStatus,
    Subscription,
    SubscriptionStatus,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepStatus,
)
from app.models.order import Order, OrderStatus
from app.models.quote import BillingInterval, BillingType, QuoteLineType
from app.models.user import UserRole
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository


class LifecycleService:
    HARDWARE_WORKFLOW_STAGES: list[tuple[str, str]] = [
        ('hw_ordered', 'Hardware Ordered'),
        ('hw_supplier', 'Supplier Allocation'),
        ('hw_qc', 'Hardware QC'),
        ('hw_shipping', 'Shipping'),
        ('hw_delivery', 'Delivery'),
    ]
    SERVICE_WORKFLOW_STAGES: list[tuple[str, str]] = [
        ('svc_provisioning', 'Service Provisioning'),
        ('svc_activation', 'Service Activation'),
        ('svc_monitoring', 'Monitoring Ready'),
    ]

    def __init__(self, db):
        self.db = db
        self.user_repo = UserRepository(db)
        self.order_repo = OrderRepository(db)

    @staticmethod
    def _add_months(source: date, months: int) -> date:
        month_index = source.month - 1 + months
        year = source.year + month_index // 12
        month = month_index % 12 + 1
        day = min(source.day, 28)
        return date(year, month, day)

    @staticmethod
    def _is_admin(role: str | None) -> bool:
        return role in {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}

    @staticmethod
    def _stage_index_for_order_status(status: OrderStatus, stage_count: int) -> int:
        if stage_count <= 0:
            return 0
        if status == OrderStatus.SUBMITTED:
            return 0
        if status in {OrderStatus.PROCESSING, OrderStatus.VENDOR_ORDERED}:
            return min(1, stage_count - 1)
        if status == OrderStatus.SHIPPED:
            return min(max(stage_count - 2, 0), stage_count - 1)
        if status in {OrderStatus.DELIVERED, OrderStatus.ACTIVE}:
            return stage_count - 1
        return 0

    @staticmethod
    def _order_status_for_stage(stage_key: str, workflow_status: WorkflowStatus) -> OrderStatus:
        if workflow_status == WorkflowStatus.COMPLETED:
            return OrderStatus.ACTIVE
        if stage_key == 'hw_shipping':
            return OrderStatus.SHIPPED
        if stage_key == 'shipped':
            return OrderStatus.SHIPPED
        if stage_key.startswith('hw_') or stage_key.startswith('svc_'):
            return OrderStatus.PROCESSING
        if stage_key in {'ordered', 'supplier', 'qc', 'delivered'}:
            return OrderStatus.PROCESSING
        return OrderStatus.SUBMITTED

    @staticmethod
    def _workflow_template_for_order(order: Order) -> tuple[str, list[tuple[str, str]]]:
        has_hardware = any(line.line_type == QuoteLineType.DEVICE for line in order.lines)
        has_service = any(line.line_type == QuoteLineType.SERVICE for line in order.lines)

        if has_hardware and has_service:
            return 'mixed_fulfillment', LifecycleService.HARDWARE_WORKFLOW_STAGES + LifecycleService.SERVICE_WORKFLOW_STAGES
        if has_hardware:
            return 'hardware_fulfillment', LifecycleService.HARDWARE_WORKFLOW_STAGES
        return 'service_fulfillment', LifecycleService.SERVICE_WORKFLOW_STAGES

    def _assert_user_exists(self, current_user: dict):
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')

    def _assert_order_access(self, current_user: dict, order: Order) -> None:
        if self._is_admin(current_user.get('role')):
            if str(order.tenant_id) != current_user['tenant_id']:
                raise ForbiddenError('Order not found in your tenant')
            return
        if str(order.created_by) != current_user['user_id']:
            raise ForbiddenError('Order not found for current user')

    def _assert_admin(self, current_user: dict) -> None:
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can perform this action')

    @staticmethod
    def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except (ValueError, TypeError):
            raise NotFoundError(f'Invalid {field_name}')

    def _get_order_for_actor(self, current_user: dict, order_id: str) -> Order:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError('Order not found')
        self._assert_order_access(current_user, order)
        return order

    def ensure_order_lifecycle(self, order: Order, current_user: dict) -> Contract:
        existing = self.db.scalar(select(Contract).where(Contract.order_id == order.id))
        if existing:
            return existing

        contract = Contract(
            tenant_id=order.tenant_id,
            order_id=order.id,
            created_by=self._parse_uuid(current_user['user_id'], field_name='user_id'),
            status=ContractStatus.ACTIVE,
            term_months=12,
            sla_tier='STANDARD',
            entitlements={
                'monitoring': True,
                'support_tier': 'STANDARD',
                'change_requests': True,
            },
            start_date=date.today(),
        )
        self.db.add(contract)
        self.db.flush()

        self._create_assets_from_order(order, contract, current_user)
        self._create_subscriptions_from_order(order, contract)
        self._create_workflow_for_order(order)
        return contract

    def _create_assets_from_order(self, order: Order, contract: Contract, current_user: dict) -> None:
        for line in order.lines:
            if line.line_type != QuoteLineType.DEVICE:
                continue
            metadata = line.metadata_json or {}
            attrs = metadata.get('attributes') or {}
            asset = Asset(
                tenant_id=order.tenant_id,
                contract_id=contract.id,
                order_line_id=line.id,
                name=line.name,
                sku=line.sku,
                vendor=line.vendor,
                asset_type=str(metadata.get('category') or 'device'),
                status=AssetStatus.ACTIVE,
                owner_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id'),
                location=attrs.get('location'),
                serial_number=attrs.get('serial_number'),
                metadata_json={
                    'source_order_id': str(order.id),
                    'qty': line.qty,
                    'billing': line.billing.value if hasattr(line.billing, 'value') else str(line.billing),
                },
            )
            self.db.add(asset)

    def _create_subscriptions_from_order(self, order: Order, contract: Contract) -> None:
        for line in order.lines:
            if line.billing != BillingType.RECURRING:
                continue
            if line.interval not in {BillingInterval.MONTH, BillingInterval.YEAR}:
                continue
            start = date.today()
            next_billing = self._add_months(start, 1 if line.interval == BillingInterval.MONTH else 12)
            subscription = Subscription(
                tenant_id=order.tenant_id,
                contract_id=contract.id,
                order_line_id=line.id,
                name=line.name,
                sku=line.sku,
                vendor=line.vendor,
                qty=line.qty,
                unit_price=float(line.unit_price),
                currency='USD',
                interval=line.interval,
                status=SubscriptionStatus.ACTIVE,
                start_date=start,
                next_billing_date=next_billing,
                metadata_json={
                    'source_order_id': str(order.id),
                    'parent_line_id': str(line.parent_line_id) if line.parent_line_id else None,
                    'line_type': line.line_type.value if hasattr(line.line_type, 'value') else str(line.line_type),
                },
            )
            self.db.add(subscription)

    def _create_workflow_for_order(self, order: Order) -> WorkflowInstance:
        existing = self.db.scalar(
            select(WorkflowInstance)
            .where(WorkflowInstance.order_id == order.id)
            .options(selectinload(WorkflowInstance.steps))
        )
        if existing:
            return existing

        template_key, stages = self._workflow_template_for_order(order)
        if not stages:
            stages = self.SERVICE_WORKFLOW_STAGES

        workflow = WorkflowInstance(
            tenant_id=order.tenant_id,
            order_id=order.id,
            template_key=template_key,
            status=WorkflowStatus.ACTIVE,
            current_stage=stages[0][0],
        )
        self.db.add(workflow)
        self.db.flush()

        reached_index = self._stage_index_for_order_status(order.status, len(stages))
        mark_complete = order.status in {OrderStatus.DELIVERED, OrderStatus.ACTIVE}
        now = datetime.now(timezone.utc)
        for sequence, (stage_key, label) in enumerate(stages):
            if mark_complete or sequence < reached_index:
                status = WorkflowStepStatus.DONE
                started_at = now
                completed_at = now
            elif sequence == reached_index and not mark_complete:
                status = WorkflowStepStatus.IN_PROGRESS
                started_at = now
                completed_at = None
                workflow.current_stage = stage_key
            else:
                status = WorkflowStepStatus.PENDING
                started_at = None
                completed_at = None

            step = WorkflowStep(
                workflow_instance_id=workflow.id,
                stage_key=stage_key,
                display_name=label,
                sequence=sequence,
                status=status,
                retries=0,
                started_at=started_at,
                completed_at=completed_at,
                metadata_json={},
            )
            self.db.add(step)

        if mark_complete or reached_index >= len(stages) - 1:
            workflow.status = WorkflowStatus.COMPLETED
            workflow.current_stage = stages[-1][0]
        return workflow

    def list_contracts(self, current_user: dict) -> list[Contract]:
        self._assert_user_exists(current_user)
        tenant_id = self._parse_uuid(current_user['tenant_id'], field_name='tenant_id')
        user_id = self._parse_uuid(current_user['user_id'], field_name='user_id')
        stmt = (
            select(Contract)
            .where(Contract.tenant_id == tenant_id)
            .order_by(desc(Contract.created_at))
        )
        if not self._is_admin(current_user.get('role')):
            stmt = stmt.where(Contract.created_by == user_id)
        return list(self.db.scalars(stmt).all())

    def list_subscriptions(self, current_user: dict, status: SubscriptionStatus | None = None) -> list[Subscription]:
        self._assert_user_exists(current_user)
        tenant_id = self._parse_uuid(current_user['tenant_id'], field_name='tenant_id')
        user_id = self._parse_uuid(current_user['user_id'], field_name='user_id')
        stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
        if not self._is_admin(current_user.get('role')):
            stmt = stmt.join(Contract, Subscription.contract_id == Contract.id).where(Contract.created_by == user_id)
        if status:
            stmt = stmt.where(Subscription.status == status)
        stmt = stmt.order_by(desc(Subscription.created_at))
        return list(self.db.scalars(stmt).all())

    def update_subscription_status(
        self,
        current_user: dict,
        subscription_id: str,
        status: SubscriptionStatus,
    ) -> Subscription:
        self._assert_user_exists(current_user)
        self._assert_admin(current_user)

        subscription_uuid = self._parse_uuid(subscription_id, field_name='subscription_id')
        subscription = self.db.get(Subscription, subscription_uuid)
        if not subscription:
            raise NotFoundError('Subscription not found')
        if str(subscription.tenant_id) != current_user['tenant_id']:
            raise ForbiddenError('Subscription not found in your tenant')

        subscription.status = status
        if status == SubscriptionStatus.CANCELLED:
            subscription.end_date = date.today()
        if status == SubscriptionStatus.ACTIVE:
            subscription.end_date = None
            if subscription.next_billing_date is None:
                delta = 1 if subscription.interval == BillingInterval.MONTH else 12
                subscription.next_billing_date = self._add_months(date.today(), delta)

        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def list_assets(self, current_user: dict) -> list[Asset]:
        self._assert_user_exists(current_user)
        tenant_id = self._parse_uuid(current_user['tenant_id'], field_name='tenant_id')
        user_id = self._parse_uuid(current_user['user_id'], field_name='user_id')
        stmt = (
            select(Asset)
            .where(Asset.tenant_id == tenant_id)
            .order_by(desc(Asset.created_at))
        )
        if not self._is_admin(current_user.get('role')):
            stmt = stmt.join(Contract, Asset.contract_id == Contract.id).where(Contract.created_by == user_id)
        return list(self.db.scalars(stmt).all())

    def get_order_workflow(self, current_user: dict, order_id: str) -> WorkflowInstance:
        self._assert_user_exists(current_user)
        order = self._get_order_for_actor(current_user, order_id)

        workflow = self.db.scalar(
            select(WorkflowInstance)
            .where(WorkflowInstance.order_id == order.id)
            .options(selectinload(WorkflowInstance.steps))
        )
        if workflow:
            return workflow

        self.ensure_order_lifecycle(order, current_user)
        self.db.commit()
        workflow = self.db.scalar(
            select(WorkflowInstance)
            .where(WorkflowInstance.order_id == order.id)
            .options(selectinload(WorkflowInstance.steps))
        )
        if not workflow:
            raise NotFoundError('Workflow not found')
        return workflow

    def advance_order_workflow(self, current_user: dict, order_id: str) -> WorkflowInstance:
        self._assert_user_exists(current_user)
        self._assert_admin(current_user)
        workflow = self.get_order_workflow(current_user, order_id)
        order = self._get_order_for_actor(current_user, order_id)

        steps = sorted(workflow.steps, key=lambda step: step.sequence)
        active = next((step for step in steps if step.status == WorkflowStepStatus.IN_PROGRESS), None)
        now = datetime.now(timezone.utc)

        if active:
            active.status = WorkflowStepStatus.DONE
            active.completed_at = now

        next_pending = next((step for step in steps if step.status == WorkflowStepStatus.PENDING), None)
        if next_pending:
            next_pending.status = WorkflowStepStatus.IN_PROGRESS
            next_pending.started_at = next_pending.started_at or now
            workflow.current_stage = next_pending.stage_key
            workflow.status = WorkflowStatus.ACTIVE
        else:
            workflow.status = WorkflowStatus.COMPLETED
            workflow.current_stage = steps[-1].stage_key if steps else workflow.current_stage

        order.status = self._order_status_for_stage(workflow.current_stage, workflow.status)
        self.db.commit()
        self.db.refresh(workflow)

        refreshed = self.db.scalar(
            select(WorkflowInstance)
            .where(WorkflowInstance.id == workflow.id)
            .options(selectinload(WorkflowInstance.steps))
        )
        if not refreshed:
            raise NotFoundError('Workflow not found')
        return refreshed
