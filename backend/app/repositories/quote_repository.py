import uuid
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload
from app.models.quote import Quote, QuoteLine


class QuoteRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Quote:
        quote = Quote(**kwargs)
        self.db.add(quote)
        self.db.flush()
        return quote

    def get_by_id(self, quote_id: str) -> Quote | None:
        try:
            stmt = (
                select(Quote)
                .where(Quote.id == uuid.UUID(quote_id))
                .options(selectinload(Quote.lines), selectinload(Quote.deal_pricing))
            )
            return self.db.scalar(stmt)
        except (TypeError, ValueError):
            return None

    def add_line(self, **kwargs) -> QuoteLine:
        line = QuoteLine(**kwargs)
        self.db.add(line)
        self.db.flush()
        return line

    def list_for_user(self, user_id: str) -> list[Quote]:
        stmt = (
            select(Quote)
            .where(Quote.created_by == uuid.UUID(user_id))
            .options(selectinload(Quote.lines), selectinload(Quote.deal_pricing))
            .order_by(desc(Quote.created_at))
        )
        return list(self.db.scalars(stmt).all())

    def list_for_tenant(self, tenant_id: str) -> list[Quote]:
        stmt = (
            select(Quote)
            .where(Quote.tenant_id == uuid.UUID(tenant_id))
            .options(selectinload(Quote.lines), selectinload(Quote.deal_pricing))
            .order_by(desc(Quote.created_at))
        )
        return list(self.db.scalars(stmt).all())
