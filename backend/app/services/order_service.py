from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.order import OrderStatus
from app.models.user import UserRole
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_logger import audit


class OrderService:
    def __init__(self, db):
        self.db = db
        self.order_repo = OrderRepository(db)
        self.user_repo = UserRepository(db)

    def _assert_user_exists(self, current_user: dict):
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')

    @staticmethod
    def _is_admin(role: str | None) -> bool:
        return role in {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}

    def list_orders(self, current_user: dict, *, effective_tenant_id: str | None = None):
        # BUG-TENANT-001: an admin lists the effective tenant (SUPER_ADMIN
        # switcher), not just their JWT home tenant. For non-admins this is
        # always their own tenant, preserving isolation.
        self._assert_user_exists(current_user)
        if self._is_admin(current_user.get('role')):
            tenant_id = effective_tenant_id or current_user['tenant_id']
            return self.order_repo.list_for_tenant(tenant_id)
        return self.order_repo.list_for_user(current_user['user_id'])

    def get_order(self, current_user: dict, order_id: str):
        self._assert_user_exists(current_user)
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError('Order not found')

        if self._is_admin(current_user.get('role')):
            if str(order.tenant_id) != current_user['tenant_id']:
                raise ForbiddenError('Order not found in your tenant')
            return order

        if str(order.created_by_user_id) != current_user['user_id']:
            raise ForbiddenError('Order not found for current user')
        return order

    def update_order(self, current_user: dict, order_id: str, updates: dict):
        self._assert_user_exists(current_user)
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Only admin can update orders')

        order = self.get_order(current_user, order_id)
        old_status = order.status

        if 'status' in updates:
            raw_status = updates.get('status')
            try:
                order.status = OrderStatus(raw_status)
            except Exception:
                allowed = ', '.join(status.value for status in OrderStatus)
                raise AppError(f'Invalid status. Allowed values: {allowed}', 422)

        if 'estimated_delivery_date' in updates:
            order.estimated_delivery_date = updates.get('estimated_delivery_date')
        if 'confirmed_delivery_date' in updates:
            order.confirmed_delivery_date = updates.get('confirmed_delivery_date')

        self.db.commit()
        if 'status' in updates and order.status != old_status:
            audit.log('order_status_changed', order_id=str(order.id),
                      old_status=old_status.value, new_status=order.status.value)
        if 'estimated_delivery_date' in updates or 'confirmed_delivery_date' in updates:
            audit.log(
                'order_delivery_date_set',
                order_id=str(order.id),
                estimated_delivery_date=str(order.estimated_delivery_date),
                confirmed_delivery_date=str(order.confirmed_delivery_date),
            )
        refreshed = self.order_repo.get_by_id(str(order.id))
        if not refreshed:
            raise NotFoundError('Order not found')
        return refreshed
