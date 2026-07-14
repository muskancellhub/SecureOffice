"""Vendor-scoped order access.

A vendor's own tenant_id IS their vendor id — orders are surfaced by joining on
OrderLine.vendor_tenant_id (see order_repository.list_for_vendor). No name lookup
is involved at request time; the legacy vendor string is only used at backfill.
Route-level permission (view_vendor_orders) is the authz gate; this service adds
strict tenant scoping so a vendor can never read an order without one of their
own lines.
"""
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository


class VendorService:
    def __init__(self, db):
        self.db = db
        self.order_repo = OrderRepository(db)
        self.user_repo = UserRepository(db)

    def _vendor_tenant_id(self, current_user: dict) -> str:
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')
        return current_user['tenant_id']

    def list_orders(self, current_user: dict):
        tenant_id = self._vendor_tenant_id(current_user)
        return self.order_repo.list_for_vendor(tenant_id)

    def get_order(self, current_user: dict, order_id: str):
        tenant_id = self._vendor_tenant_id(current_user)
        order = self.order_repo.get_by_id(order_id)
        # Treat "order exists but has no line supplied by this vendor" as a 404 —
        # don't confirm the existence of orders outside the vendor's scope (IDOR).
        if not order or not self.vendor_lines(order, tenant_id):
            raise NotFoundError('Order not found')
        return order

    @staticmethod
    def vendor_lines(order, vendor_tenant_id: str) -> list:
        return [
            line for line in order.lines
            if line.vendor_tenant_id is not None and str(line.vendor_tenant_id) == str(vendor_tenant_id)
        ]
