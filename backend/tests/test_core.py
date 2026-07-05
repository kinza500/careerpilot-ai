"""Tests that run without a database or network — they cover the parts most
important to get right: CV encryption round-trip and the cosine ranking math."""
import os

os.environ.setdefault("CV_ENCRYPTION_KEY", "")


def test_encryption_roundtrip(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CV_ENCRYPTION_KEY", key)
    # rebuild settings cache
    from app.config import get_settings
    get_settings.cache_clear()
    from app.core import crypto
    original = b"Jane Doe -- Senior Engineer -- confidential resume"
    token = crypto.encrypt_bytes(original)
    assert token != original                 # stored form is not plaintext
    assert crypto.decrypt_bytes(token) == original
    assert len(crypto.sha256_hex(original)) == 64


def test_encryption_requires_key(monkeypatch):
    monkeypatch.setenv("CV_ENCRYPTION_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.core import crypto
    import pytest
    with pytest.raises(RuntimeError):
        crypto.encrypt_bytes(b"x")


def test_cosine_ranking_orders_by_similarity():
    from app.agents.matching_agent import cosine
    a = [1.0, 0.0, 0.0]
    near = [0.9, 0.1, 0.0]
    far = [0.0, 1.0, 0.0]
    assert cosine(a, near) > cosine(a, far)
