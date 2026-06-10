import re
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def hash_value(value: str) -> str:
    return pwd_context.hash(value)


def verify_value(plain_value: str, hashed_value: str) -> bool:
    return pwd_context.verify(plain_value, hashed_value)


def password_strength_error(password: str) -> str | None:
    """Return a human-readable reason a password is too weak, or None if it's
    strong enough. Used for high-privilege (super-admin) account setup: requires
    12+ chars with upper, lower, digit, and a symbol."""
    if not password or len(password) < 12:
        return 'Password must be at least 12 characters long.'
    if len(password) > 128:
        return 'Password must be at most 128 characters long.'
    if not re.search(r'[a-z]', password):
        return 'Password must include a lowercase letter.'
    if not re.search(r'[A-Z]', password):
        return 'Password must include an uppercase letter.'
    if not re.search(r'\d', password):
        return 'Password must include a number.'
    if not re.search(r'[^A-Za-z0-9]', password):
        return 'Password must include a symbol.'
    return None
