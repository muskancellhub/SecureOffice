from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class AddCartLineRequest(BaseModel):
    """Phase 7: cart lines are component-model only.

    Either a configured product (``product_id`` + optional ``selections`` from
    the bundling configurator) or a single standalone component (D10).
    """

    product_id: UUID | None = None
    component_id: UUID | None = None
    # {component_id: qty} — optional components to include (configurator).
    selections: dict[str, int] = Field(default_factory=dict)
    quantity: int = Field(default=1, ge=1)
    financial_model: str = Field(default='CAPEX', pattern='^(CAPEX|OPEX)$')
    interval: str = Field(default='MONTH', pattern='^(MONTH|YEAR)$')
    applies_to_line_id: UUID | None = None
    # BUG-BOM-CART-PRICE-001: the per-product price shown in the source design BOM,
    # so the cart can flag when its (re-priced) value differs. Optional — only the
    # "order this design" flow sends it.
    source_unit_price: float | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def _exactly_one_source(self):
        if bool(self.product_id) == bool(self.component_id):
            raise ValueError('Provide exactly one of product_id or component_id')
        return self


class UpdateCartLineRequest(BaseModel):
    quantity: int | None = Field(default=None, ge=1)


class CartLineResponse(BaseModel):
    id: str
    product_id: str | None = None
    component_id: str | None = None
    component_type: str | None = None
    item_name: str
    item_type: str
    category: str | None
    billing_cycle: str | None
    financial_model: str | None = None
    financed: bool = False
    standalone: bool = False
    is_parent: bool = False
    quantity: int
    unit_price: float
    currency: str
    line_total: float
    applies_to_line_id: str | None
    applies_to_item_name: str | None
    created_at: datetime


class CartResponse(BaseModel):
    id: str
    status: str
    lines: list[CartLineResponse]
    one_time_subtotal: float
    monthly_subtotal: float
    estimated_12_month_total: float
    currency: str
    # BUG-CART-003: non-blocking advisories (e.g. unusually high-value lines).
    warnings: list[str] = Field(default_factory=list)
    # BUG-CART-SETUP-001: whether setup & deployment is actually included, derived
    # from cart contents (managed services bundle deployment) — not hard-coded.
    setup_included: bool = False
