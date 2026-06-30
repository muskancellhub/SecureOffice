"""Cart on the component model (Phase 7 WS4).

Two ways into the cart:
  * a configured product — the bundling configurator confirms a
    ``{product_id, selections}`` assembly; the engine prices the tree and the
    cart stores the DEVICE parent line plus child component lines
    (``applies_to_line_id``);
  * a standalone component (D10) — "one more line" / "just a SIM" — priced
    alone; a ``requires_component_type='DEVICE'`` component must attach to a
    device line already in the cart or to an existing ordered device, and is
    capacity-checked against that device's ``capacity``/``consumes`` metadata.

Every price comes from ComponentPricingService for the cart's tenant.
"""
from __future__ import annotations

import uuid as uuid_mod

from sqlalchemy import select

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.order import Order, OrderLine
from app.models.product import ComponentType, Product, ProductComponent
from app.repositories.cart_repository import CartRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_logger import audit
from app.services.capacity_service import check_capacity, format_violations
from app.services.component_pricing_service import ComponentPricingService

# Component types that cannot stand alone in a NEW assembly (spec §5) — they
# need a device, either in the same cart or already owned.
REQUIRES_DEVICE_TYPES = {
    ComponentType.LINE_CHARGE.value,
    ComponentType.SIM.value,
    ComponentType.BACKUP_SIM.value,
}


def _enum_str(val) -> str:
    """Render an enum's .value, tolerating a plain string/None.

    Some sources (and SERVICE rows loaded on SQLite) yield a raw string for an
    enum column, so calling .value blindly raises AttributeError
    (BUG-CART-001 / TC0320). Handle enum, str, and None.
    """
    if val is None:
        return ''
    return val.value if hasattr(val, 'value') else str(val)


class CartService:
    def __init__(self, db):
        self.db = db
        self.cart_repo = CartRepository(db)
        self.user_repo = UserRepository(db)
        self.pricing = ComponentPricingService(db)

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

    # ── snapshots ────────────────────────────────────────────────────────────
    @staticmethod
    def _snapshot_from_engine_line(product: Product, result: dict, line: dict, *, standalone: bool = False) -> dict:
        return {
            'name': line['label'],
            'sku': line['vendor_component_sku'],
            'type': 'DEVICE' if line['component_type'] == ComponentType.DEVICE.value else 'SERVICE',
            'category': (product.attributes or {}).get('category'),
            'component_type': line['component_type'],
            'billing': line['billing'],
            'billing_cycle': 'MONTHLY' if line['billing'] == 'RECURRING' else 'ONE_TIME',
            'interval': line['interval'],
            'financed': line['financed'],
            'financial_model': result['financial_model'],
            'term_months': result['term_months'],
            'margin_pct': float(line['margin_pct']),
            'margin_source': line['margin_source'],
            'vendor_cost': float(line['vendor_cost']),
            'monthly_unit': float(line['monthly_unit']),
            'one_time_unit': float(line['one_time_unit']),
            'product_sku': product.sku,
            'product_name': product.name,
            'price_editable': line.get('price_editable', True),
            'standalone': standalone,
            'source': 'component_engine',
        }

    # ── capacity helpers ─────────────────────────────────────────────────────
    def _consumes_for_components(self, component_ids: list) -> dict:
        if not component_ids:
            return {}
        rows = self.db.scalars(
            select(ProductComponent).where(ProductComponent.id.in_(component_ids))
        ).all()
        return {str(c.id): (c.attributes or {}).get('consumes') for c in rows}

    @staticmethod
    def _scaled_capacity(product: Product, device_qty: int) -> dict:
        capacity = (product.attributes or {}).get('capacity') or {}
        return {k: v * max(1, int(device_qty)) for k, v in capacity.items()}

    def _assert_capacity(self, product: Product, device_qty: int, consumers: list) -> None:
        violations = check_capacity(self._scaled_capacity(product, device_qty), consumers)
        if violations:
            raise AppError(f'Device capacity exceeded — {format_violations(violations)}', 409)

    # ── add a configured product (configurator confirm, D9) ─────────────────
    def _add_product_lines(self, current_user: dict, cart, *, product_id, selections, quantity,
                           financial_model, interval) -> None:
        product = self.db.get(Product, self._parse_uuid(product_id, 'product_id'))
        if product is None or not product.is_active:
            raise NotFoundError('Product not found')

        result = self.pricing.price_product(
            product.id, financial_model=financial_model, interval=interval,
            selections=selections or {}, tenant_id=current_user['tenant_id'],
        )
        if not result['lines']:
            raise AppError('Selection contains no purchasable components', 400)

        # Capacity: every selected consumer vs the device's (scaled) capacity.
        consumes = self._consumes_for_components(
            [self._parse_uuid(l['component_id'], 'component_id') for l in result['lines']]
        )
        consumers = [(consumes.get(l['component_id']), l['qty']) for l in result['lines']]
        self._assert_capacity(product, 1, consumers)

        device_line = next(
            (l for l in result['lines'] if l['component_type'] == ComponentType.DEVICE.value), None
        )
        ordered = sorted(result['lines'], key=lambda l: 0 if l is device_line else 1)
        quantity = max(1, int(quantity or 1))

        # Single non-device product (e.g. the standalone Multiline line item):
        # merge a repeat add into the existing matching cart line instead of
        # creating a duplicate. Configured bundles (a device + selections) keep
        # their own distinct lines.
        if device_line is None and len(ordered) == 1 and not selections:
            only = ordered[0]
            existing = self.cart_repo.get_matching_line(
                cart_id=cart.id,
                component_id=self._parse_uuid(only['component_id'], 'component_id'),
                applies_to_line_id=None,
            )
            if existing is not None:
                existing.quantity = int(existing.quantity) + int(only['qty']) * quantity
                existing.unit_price = float(only['unit_price'])
                existing.price_snapshot = {
                    **self._snapshot_from_engine_line(product, result, only),
                    'is_parent': True,
                    'selections': None,
                }
                self.db.flush()
                audit.log(
                    'cart_item_added', product_id=str(product.id), item_sku=product.sku,
                    item_name=product.name, unit_price=float(only['unit_price']),
                    quantity=quantity, line_count=1, financial_model=result['financial_model'],
                )
                return

        parent_db_line = None
        for line in ordered:
            is_parent = device_line is not None and line is device_line
            created = self.cart_repo.add_line(
                cart_id=cart.id,
                product_id=product.id,
                component_id=self._parse_uuid(line['component_id'], 'component_id'),
                quantity=int(line['qty']) * quantity,
                unit_price=float(line['unit_price']),
                currency='USD',
                price_snapshot={
                    **self._snapshot_from_engine_line(product, result, line),
                    'is_parent': is_parent,
                    'selections': {str(k): int(v) for k, v in (selections or {}).items()} if is_parent else None,
                },
                applies_to_line_id=None if (is_parent or parent_db_line is None) else parent_db_line.id,
            )
            if is_parent:
                parent_db_line = created

        # BUG-AUD-005: include the human-readable name and the device unit price
        # for financial auditability.
        priced_line = device_line or (ordered[0] if ordered else None)
        audit.log(
            'cart_item_added',
            product_id=str(product.id),
            item_sku=product.sku,
            item_name=product.name,
            unit_price=float(priced_line['unit_price']) if priced_line else 0.0,
            quantity=quantity,
            line_count=len(ordered),
            financial_model=result['financial_model'],
        )

    # ── add a standalone component (à-la-carte, D10) ─────────────────────────
    def _attached_consumers(self, cart, parent_line) -> list:
        children = [l for l in cart.lines if l.applies_to_line_id == parent_line.id and l.component_id]
        consumes = self._consumes_for_components([l.component_id for l in children])
        return [(consumes.get(str(l.component_id)), l.quantity) for l in children]

    def _resolve_standalone_attach(self, current_user: dict, cart, component: ProductComponent,
                                   product: Product, qty: int, applies_to_line_id):
        """Validate the requires-a-device rule + capacity; returns the cart
        parent line id (or None when attaching to an already-ordered device)."""
        requires = (component.attributes or {}).get('requires_component_type')
        needs_device = requires == 'DEVICE' or _enum_str(component.component_type) in REQUIRES_DEVICE_TYPES

        if applies_to_line_id:
            target = self._ensure_line_in_cart(cart, applies_to_line_id)
            if not target.component_id or (target.price_snapshot or {}).get('component_type') != ComponentType.DEVICE.value:
                raise AppError('Components can only attach to a device line', 400)
            if str(target.product_id) == str(product.id):
                # Same-product add-on (extra line / SIM) — capacity-enforced.
                consumers = self._attached_consumers(cart, target)
                consumers.append(((component.attributes or {}).get('consumes'), qty))
                target_product = self.db.get(Product, target.product_id)
                self._assert_capacity(target_product, target.quantity, consumers)
                return target.id
            # Cross-product service attach (e.g. a managed-router tier on a
            # CDW router) — gated by the service's applies_to_categories.
            if component.component_type == ComponentType.DEVICE:
                raise AppError('A device cannot attach to another device line', 400)
            allowed = (product.attributes or {}).get('applies_to_categories') or []
            target_category = (target.price_snapshot or {}).get('category')
            if allowed and target_category not in allowed:
                raise ForbiddenError('Service cannot attach to selected line category')
            return target.id

        if not needs_device:
            return None

        # No device in this purchase — attach to an existing ordered device
        # ("add one more line" on a live contract).
        device_order_line = self.db.scalar(
            select(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                Order.tenant_id == self._parse_uuid(current_user['tenant_id'], 'tenant_id'),
                OrderLine.product_id == product.id,
                OrderLine.component_type == ComponentType.DEVICE.value,
            )
            .order_by(OrderLine.created_at.desc())
        )
        if device_order_line is None:
            raise AppError(
                f'{_enum_str(component.component_type)} requires a device — add the device first '
                'or order it before buying this add-on', 400
            )
        siblings = self.db.scalars(
            select(OrderLine).where(
                OrderLine.order_id == device_order_line.order_id,
                OrderLine.product_id == product.id,
                OrderLine.component_id.is_not(None),
            )
        ).all()
        consumes = self._consumes_for_components([l.component_id for l in siblings])
        consumers = [(consumes.get(str(l.component_id)), l.qty) for l in siblings]
        consumers.append(((component.attributes or {}).get('consumes'), qty))
        self._assert_capacity(product, device_order_line.qty, consumers)
        return None

    def _add_standalone_component(self, current_user: dict, cart, *, component_id, quantity,
                                  financial_model, interval, applies_to_line_id) -> None:
        component = self.db.get(ProductComponent, self._parse_uuid(component_id, 'component_id'))
        if component is None or not component.is_active:
            raise NotFoundError('Component not found')
        product = self.db.get(Product, component.product_id)
        if product is None or not product.is_active:
            raise NotFoundError('Product not found')
        if component.component_type == ComponentType.DEVICE:
            raise AppError('Add devices through the product configurator', 400)

        quantity = max(1, int(quantity or 1))
        parent_line_id = self._resolve_standalone_attach(
            current_user, cart, component, product, quantity, applies_to_line_id
        )

        result = self.pricing.price_standalone_component(
            component.id, qty=quantity, financial_model=financial_model,
            interval=interval, tenant_id=current_user['tenant_id'],
        )
        line = result['lines'][0]

        existing = self.cart_repo.get_matching_line(
            cart_id=cart.id, component_id=component.id, applies_to_line_id=parent_line_id
        )
        snapshot = {
            **self._snapshot_from_engine_line(product, result, line, standalone=parent_line_id is None),
            'is_parent': False,
        }
        if existing:
            existing.quantity = quantity
            existing.unit_price = float(line['unit_price'])
            existing.price_snapshot = snapshot
        else:
            self.cart_repo.add_line(
                cart_id=cart.id,
                product_id=product.id,
                component_id=component.id,
                quantity=quantity,
                unit_price=float(line['unit_price']),
                currency='USD',
                price_snapshot=snapshot,
                applies_to_line_id=parent_line_id,
            )
        audit.log(
            'cart_item_added',
            component_id=str(component.id),
            item_sku=component.vendor_component_sku,
            item_name=component.label,
            unit_price=float(line['unit_price']),
            quantity=quantity,
            standalone=parent_line_id is None,
            applies_to_line_id=str(parent_line_id) if parent_line_id else None,
            replaced_existing_line=existing is not None,
        )

    # ── public API ───────────────────────────────────────────────────────────
    def add_line(
        self,
        current_user: dict,
        *,
        product_id=None,
        component_id=None,
        selections: dict | None = None,
        quantity: int = 1,
        financial_model: str = 'CAPEX',
        interval: str = 'MONTH',
        applies_to_line_id=None,
    ):
        self._assert_user_exists(current_user)
        if bool(product_id) == bool(component_id):
            raise AppError('Provide exactly one of product_id or component_id', 400)
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])

        if product_id:
            self._add_product_lines(
                current_user, cart, product_id=product_id, selections=selections,
                quantity=quantity, financial_model=financial_model, interval=interval,
            )
        else:
            self._add_standalone_component(
                current_user, cart, component_id=component_id, quantity=quantity,
                financial_model=financial_model, interval=interval,
                applies_to_line_id=applies_to_line_id,
            )
        self.db.commit()
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
        # BUG-AUD-006: spec field names — quantity_removed + human-readable name.
        audit.log(
            'cart_item_removed',
            line_id=line_id,
            component_id=str(line.component_id) if line.component_id else None,
            item_name=(line.price_snapshot or {}).get('name'),
            quantity_removed=line.quantity,
            detached_lines=len(attached),
        )
        return self.cart_repo.get_active_cart(current_user['user_id'], current_user['tenant_id'])

    def clear_cart(self, current_user: dict):
        """Empty the active cart in one atomic operation (BUG-CART-002)."""
        self._assert_user_exists(current_user)
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])
        removed = self.cart_repo.delete_all_lines(cart.id)
        self.db.commit()
        audit.log('cart_cleared', cart_id=str(cart.id), lines_removed=removed)
        return self.cart_repo.get_active_cart(current_user['user_id'], current_user['tenant_id'])

    def update_line(self, current_user: dict, line_id: str, *, quantity: int | None):
        """Change a line's quantity. A device parent scales the assembly's
        capacity; children are re-checked against it."""
        self._assert_user_exists(current_user)
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])
        line = self._ensure_line_in_cart(cart, line_id)
        old_quantity = line.quantity

        if quantity is not None and quantity != line.quantity:
            snapshot = line.price_snapshot or {}
            is_device = snapshot.get('component_type') == ComponentType.DEVICE.value
            product = self.db.get(Product, line.product_id) if line.product_id else None

            if is_device and product is not None:
                # Scale children proportionally with the device count.
                ratio_children = self.cart_repo.list_attached_service_lines(cart.id, line.id)
                for child in ratio_children:
                    per_device = max(1, child.quantity // max(1, old_quantity))
                    child.quantity = per_device * quantity
                line.quantity = quantity
            else:
                line.quantity = quantity
                if line.applies_to_line_id and product is not None:
                    parent = self.cart_repo.get_line_by_id(str(line.applies_to_line_id))
                    if parent is not None:
                        consumers = self._attached_consumers(cart, parent)
                        self._assert_capacity(product, parent.quantity, consumers)

        self.db.commit()
        audit.log(
            'cart_item_updated',
            line_id=line_id,
            old_quantity=old_quantity,
            new_quantity=line.quantity,
        )
        return self.cart_repo.get_active_cart(current_user['user_id'], current_user['tenant_id'])

    @staticmethod
    def _parse_uuid(value, field_name: str):
        try:
            return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)
