import time

import jwt
from app.core.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.users.models import User


def test_password_hash_roundtrip():
    hashed = get_password_hash("securepassword")
    assert hashed != "securepassword"
    assert verify_password("securepassword", hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_create_access_token_uses_default_expiry():
    token = create_access_token(data={"sub": "user@example.com"})
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "user@example.com"
    now = time.time()
    assert payload["exp"] > now
    assert payload["exp"] <= now + 16 * 60


def test_user_model_str_returns_email():
    assert str(User(email="person@example.com")) == "person@example.com"
