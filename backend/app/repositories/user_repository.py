import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User, AuthProvider


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower().strip()))

    def get_by_id(self, user_id: str) -> User | None:
        try:
            return self.db.get(User, uuid.UUID(user_id))
        except (ValueError, TypeError):
            return None

    def get_by_provider_id(self, provider: AuthProvider, provider_id: str) -> User | None:
        return self.db.scalar(select(User).where(User.provider == provider, User.provider_id == provider_id))

    def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self.db.add(user)
        self.db.flush()
        return user

    def list_all(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at.desc())).all())

    def list_by_tenant(self, tenant_id: str) -> list[User]:
        return list(
            self.db.scalars(
                select(User).where(User.tenant_id == uuid.UUID(tenant_id)).order_by(User.created_at.desc())
            ).all()
        )
