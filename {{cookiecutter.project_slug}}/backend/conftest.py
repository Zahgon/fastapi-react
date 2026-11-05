import typing as t

import pytest
from rest_framework.test import APIClient

from app.core import security
from app.users.models import User


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def test_password() -> str:
    return "securepassword"


def get_password_hash() -> str:
    """Password hashing can be expensive so a mock will be much faster."""
    return "supersecrethash"


@pytest.fixture
def test_user(db) -> User:
    return User.objects.create(
        email="fake@email.com",
        hashed_password=get_password_hash(),
        is_active=True,
    )


@pytest.fixture
def test_superuser(db) -> User:
    return User.objects.create(
        email="fakeadmin@email.com",
        hashed_password=get_password_hash(),
        is_superuser=True,
    )


def verify_password_mock(first: str, second: str) -> bool:
    return True


@pytest.fixture
def user_token_headers(
    client: APIClient, test_user: User, test_password: str, monkeypatch
) -> t.Dict[str, str]:
    monkeypatch.setattr(security, "verify_password", verify_password_mock)

    login_data = {
        "username": test_user.email,
        "password": test_password,
    }
    r = client.post("/api/token", login_data)
    tokens = r.json()
    a_token = tokens["access_token"]
    return {"HTTP_AUTHORIZATION": f"Bearer {a_token}"}


@pytest.fixture
def superuser_token_headers(
    client: APIClient, test_superuser: User, test_password: str, monkeypatch
) -> t.Dict[str, str]:
    monkeypatch.setattr(security, "verify_password", verify_password_mock)

    login_data = {
        "username": test_superuser.email,
        "password": test_password,
    }
    r = client.post("/api/token", login_data)
    tokens = r.json()
    a_token = tokens["access_token"]
    return {"HTTP_AUTHORIZATION": f"Bearer {a_token}"}
