class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UnauthorizedError(AppError):
    def __init__(self, message: str = 'Unauthorized'):
        super().__init__(message=message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = 'Forbidden', required_permission: str | None = None):
        super().__init__(message=message, status_code=403)
        # Carried so the central 403 handler can audit-log which permission
        # was missing (docs/LOGGING_PLAN.md §4.3) without parsing the message.
        self.required_permission = required_permission


class NotFoundError(AppError):
    def __init__(self, message: str = 'Not found'):
        super().__init__(message=message, status_code=404)
