class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UnauthorizedError(AppError):
    def __init__(self, message: str = 'Unauthorized'):
        super().__init__(message=message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = 'Forbidden'):
        super().__init__(message=message, status_code=403)


class NotFoundError(AppError):
    def __init__(self, message: str = 'Not found'):
        super().__init__(message=message, status_code=404)
