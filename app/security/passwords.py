import logging
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

logger = logging.getLogger(__name__)

# Argon2id password hasher with secure parameters (OWASP recommendation)
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception as e:
        logger.error(f"Unexpected error during password verification: {e}")
        return False

def check_needs_rehash(hashed_password: str) -> bool:
    """Check if the password hash needs an update to stronger parameters."""
    try:
        return _hasher.check_needs_rehash(hashed_password)
    except Exception:
        return False
