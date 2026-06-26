import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.encryption import EncryptionService
from app.models import User, AuthProvider


class UserRepository:
    def __init__(self, db: Session):
        self.db = db
        # Decrypt the encrypted PII columns (name, mobile) on the way out so every
        # consumer of these getters sees plaintext (docs/PII_ENCRYPTION.md §7).
        # Writes are encrypted centrally by the before_flush listener.
        self._enc = EncryptionService(db)

    def _dec(self, user: User | None) -> User | None:
        if user is not None:
            self._enc.decrypt_instance(user)
        return user

    def get_by_email(self, email: str) -> User | None:
        return self._dec(self.db.scalar(select(User).where(User.email == email.lower().strip())))

    def get_by_id(self, user_id: str) -> User | None:
        try:
            return self._dec(self.db.get(User, uuid.UUID(user_id)))
        except (ValueError, TypeError):
            return None

    def get_by_provider_id(self, provider: AuthProvider, provider_id: str) -> User | None:
        return self._dec(self.db.scalar(select(User).where(User.provider == provider, User.provider_id == provider_id)))

    def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self.db.add(user)
        self.db.flush()
        return user

    def list_all(self) -> list[User]:
        users = list(self.db.scalars(select(User).order_by(User.created_at.desc())).all())
        self._enc.decrypt_all(users)
        return users

    def list_by_tenant(self, tenant_id: str) -> list[User]:
        users = list(
            self.db.scalars(
                select(User).where(User.tenant_id == uuid.UUID(tenant_id)).order_by(User.created_at.desc())
            ).all()
        )
        self._enc.decrypt_all(users)
        return users
