"""Encryption at rest for resume bytes.

CVs are sensitive personal documents. We never store them in plaintext: the
raw uploaded bytes are encrypted with Fernet (authenticated symmetric
encryption) before they touch the database `resumes.ciphertext` column, and
decrypted only in-memory, only for the owning user, only when an agent needs
the text. The key lives in an env var / secret manager, never in the DB.
"""
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings

settings = get_settings()


def _fernet() -> Fernet:
    key = settings.cv_encryption_key
    if not key:
        raise RuntimeError(
            "CV_ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
