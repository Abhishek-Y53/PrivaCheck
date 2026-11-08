"""Argon2id password hashing and verification."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


# argon2-cffi's defaults use Argon2id with a deliberately expensive memory cost.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return a salted Argon2id PHC string. Never store or log the raw password."""
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("Password must contain between 12 and 128 characters.")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password without leaking malformed-hash errors to callers."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, TypeError):
        return False


def password_hash_needs_rehash(password_hash: str) -> bool:
    """Allow Argon2 parameters to be upgraded transparently after login."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (VerificationError, InvalidHashError, TypeError):
        return False
