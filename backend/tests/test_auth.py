import os

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

import jwt  # noqa: E402
import pytest  # noqa: E402

from app.services.auth import create_token, decode_token, hash_password, verify_password  # noqa: E402


def test_password_roundtrip():
    h = hash_password("hunter22")
    assert verify_password("hunter22", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip_and_tamper():
    token = create_token("abc123")
    assert decode_token(token) == "abc123"
    with pytest.raises(jwt.PyJWTError):
        decode_token(token[:-2] + "xx")
