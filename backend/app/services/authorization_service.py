from sqlalchemy.orm import Session
from app.core.exceptions import ForbiddenError
from app.core.permissions import effective_permissions_for_role
from app.repositories.user_repository import UserRepository


class AuthorizationService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

    def effective_permissions(self, current_user: dict) -> set[str]:
        actor = self.user_repo.get_by_id(current_user.get('user_id'))
        if not actor:
            raise ForbiddenError('Actor user not found')
        return set(effective_permissions_for_role(actor.role, actor.permissions))

    def require(self, current_user: dict, *permission_codes: str) -> set[str]:
        permissions = self.effective_permissions(current_user)
        for permission_code in permission_codes:
            if permission_code not in permissions:
                raise ForbiddenError(f'Missing permission: {permission_code}')
        return permissions
