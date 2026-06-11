from enum import Enum

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.catalog import CatalogItem, CatalogItemType
from app.repositories.cart_repository import CartRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_logger import audit


def _enum_value(value):
    """Return the underlying string for an enum, or the value unchanged if it is
    already a plain string. SQLAlchemy only coerces a column back to its Enum type
    on a fresh DB load; an attribute that was set from a string (or not reloaded)
    can still be a bare str, so ``.value`` is unsafe (BUG-CART-001)."""
    return value.value if isinstance(value, Enum) else value


class CartService:
    def __init__(self, db):
        self.db = db
        self.cart_repo = CartRepository(db)
        self.user_repo = UserRepository(db)

    def _assert_user_exists(self, current_user: dict) -> None:
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found for cart session')

    def _ensure_line_in_cart(self, cart, line_id: str):
        line = self.cart_repo.get_line_by_id(line_id)
        if not line or str(line.cart_id) != str(cart.id):
            raise NotFoundError('Cart line not found')
        return line

    def get_active_cart(self, current_user: dict):
        self._assert_user_exists(current_user)
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])
        self.db.commit()
        self.db.refresh(cart)
        return self.cart_repo.get_active_cart(current_user['user_id'], current_user['tenant_id'])

    def add_line(self, current_user: dict, *, catalog_item_id: str, quantity: int, applies_to_line_id: str | None):
        self._assert_user_exists(current_user)
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])

        item = self.db.get(CatalogItem, catalog_item_id)
        if not item or not item.is_active:
            raise NotFoundError('Catalog item not found')

        attach_line_uuid = None
        target_line = None
        if applies_to_line_id:
            target_line = self._ensure_line_in_cart(cart, applies_to_line_id)
            if item.type != CatalogItemType.SERVICE:
                raise AppError('Only service lines can attach to another cart line', 400)
            target_category = (target_line.price_snapshot or {}).get('category')
            allowed_categories = (item.attributes or {}).get('applies_to_categories', [])
            if allowed_categories and target_category not in allowed_categories:
                raise ForbiddenError('Service cannot attach to selected line category')
            attach_line_uuid = target_line.id

        # Managed services apply per selected router unit.
        effective_quantity = target_line.quantity if (item.type == CatalogItemType.SERVICE and target_line) else quantity

        snapshot = {
            'name': item.name,
            'sku': item.sku,
            'type': _enum_value(item.type),
            'category': (item.attributes or {}).get('category'),
            'attributes': item.attributes,
            'billing_cycle': _enum_value(item.billing_cycle),
        }

        existing_line = self.cart_repo.get_matching_line(
            cart_id=cart.id,
            catalog_item_id=item.id,
            applies_to_line_id=attach_line_uuid,
        )
        if existing_line:
            existing_line.quantity = effective_quantity
            existing_line.unit_price = float(item.price)
            existing_line.currency = item.currency
            existing_line.price_snapshot = snapshot
        else:
            self.cart_repo.add_line(
                cart_id=cart.id,
                catalog_item_id=item.id,
                quantity=effective_quantity,
                unit_price=float(item.price),
                currency=item.currency,
                price_snapshot=snapshot,
                applies_to_line_id=attach_line_uuid,
            )
        self.db.commit()
        audit.log(
            'service_attached_to_device' if attach_line_uuid else 'cart_item_added',
            catalog_item_id=str(item.id),
            item_sku=item.sku,
            quantity=effective_quantity,
            applies_to_line_id=str(attach_line_uuid) if attach_line_uuid else None,
            replaced_existing_line=existing_line is not None,
        )
        return self.cart_repo.get_active_cart(current_user['user_id'], current_user['tenant_id'])

    def remove_line(self, current_user: dict, line_id: str):
        self._assert_user_exists(current_user)
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])
        line = self._ensure_line_in_cart(cart, line_id)

        attached = self.cart_repo.list_attached_service_lines(cart.id, line.id)
        for s in attached:
            self.cart_repo.delete_line(s)

        self.cart_repo.delete_line(line)
        self.db.commit()
        audit.log(
            'cart_item_removed',
            line_id=line_id,
            catalog_item_id=str(line.catalog_item_id),
            quantity=line.quantity,
            detached_service_lines=len(attached),
        )
        return self.cart_repo.get_active_cart(current_user['user_id'], current_user['tenant_id'])

    def update_line(self, current_user: dict, line_id: str, *, quantity: int | None, catalog_item_id: str | None):
        self._assert_user_exists(current_user)
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])
        line = self._ensure_line_in_cart(cart, line_id)
        snapshot = line.price_snapshot or {}
        line_type = snapshot.get('type')
        old_quantity = line.quantity
        old_catalog_item_id = str(line.catalog_item_id)

        if quantity is not None:
            line.quantity = quantity
            if line_type == 'SERVICE' and line.applies_to_line_id:
                parent = self.cart_repo.get_line_by_id(str(line.applies_to_line_id))
                if parent:
                    line.quantity = parent.quantity

        if catalog_item_id:
            new_item = self.db.get(CatalogItem, catalog_item_id)
            if not new_item or not new_item.is_active:
                raise NotFoundError('Target catalog item not found')

            old_type = snapshot.get('type')
            if old_type != 'SERVICE' or new_item.type != CatalogItemType.SERVICE:
                raise AppError('Catalog item replacement is allowed only for service lines', 400)

            if line.applies_to_line_id:
                target_line = self.cart_repo.get_line_by_id(str(line.applies_to_line_id))
                target_category = (target_line.price_snapshot or {}).get('category') if target_line else None
                allowed = (new_item.attributes or {}).get('applies_to_categories', [])
                if target_category not in allowed:
                    raise ForbiddenError('Selected service tier is not valid for this attached item')

            line.catalog_item_id = new_item.id
            line.unit_price = float(new_item.price)
            line.currency = new_item.currency
            line.price_snapshot = {
                'name': new_item.name,
                'sku': new_item.sku,
                'type': _enum_value(new_item.type),
                'category': (new_item.attributes or {}).get('category'),
                'attributes': new_item.attributes,
                'billing_cycle': _enum_value(new_item.billing_cycle),
            }

        if line_type == 'DEVICE':
            attached = self.cart_repo.list_attached_service_lines(cart.id, line.id)
            for service_line in attached:
                service_line.quantity = line.quantity

        self.db.commit()
        audit.log(
            'cart_item_updated',
            line_id=line_id,
            old_quantity=old_quantity,
            new_quantity=line.quantity,
            old_catalog_item_id=old_catalog_item_id,
            new_catalog_item_id=str(line.catalog_item_id),
        )
        return self.cart_repo.get_active_cart(current_user['user_id'], current_user['tenant_id'])
