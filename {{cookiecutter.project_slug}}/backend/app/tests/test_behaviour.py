from app.core.celery_app import celery_app
from app.core.security import create_access_token, get_password_hash
from app.users.models import User


def test_signup_then_login_then_me_journey(client, db):
    signup = client.post(
        "/api/signup",
        {"username": "journey@example.com", "password": "s3cret-pass"},
    )
    assert signup.status_code == 200
    assert signup.json()["token_type"] == "bearer"

    login = client.post(
        "/api/token",
        {"username": "journey@example.com", "password": "s3cret-pass"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/v1/users/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "journey@example.com"
    assert body["is_active"] is True
    assert body["is_superuser"] is False
    assert "hashed_password" not in body
    assert "first_name" not in body
    assert "last_name" not in body


def test_superuser_crud_journey(client, superuser_token_headers):
    # `format="json"`: the test client defaults to multipart, and FastAPI read
    # a body as JSON only when the content type said JSON. A multipart POST was
    # a 422 there, so leaving the format off tested a request the original
    # never accepted.
    created = client.post(
        "/api/v1/users",
        {"email": "crud@example.com", "password": "pw123456"},
        format="json",
        **superuser_token_headers,
    )
    assert created.status_code == 200
    user_id = created.json()["id"]
    assert created.json()["email"] == "crud@example.com"
    assert created.json()["is_active"] is True
    assert created.json()["is_superuser"] is False

    listing = client.get("/api/v1/users", **superuser_token_headers)
    assert listing.status_code == 200
    assert listing["Content-Range"] == f"0-9/{len(listing.json())}"
    assert any(u["email"] == "crud@example.com" for u in listing.json())

    fetched = client.get(f"/api/v1/users/{user_id}", **superuser_token_headers)
    assert fetched.status_code == 200

    # `email` is sent because `UserEdit` inherits it from `UserBase` without a
    # default, so pydantic required it on every PUT. Omitting it here asserted
    # a partial update the original answered with a 422 -- see
    # `test_put_without_email_is_rejected` below.
    edited = client.put(
        f"/api/v1/users/{user_id}",
        {
            "email": "crud@example.com",
            "first_name": "Crud",
            "last_name": "User",
        },
        format="json",
        **superuser_token_headers,
    )
    assert edited.status_code == 200
    assert edited.json()["first_name"] == "Crud"
    assert edited.json()["last_name"] == "User"

    deleted = client.delete(
        f"/api/v1/users/{user_id}", **superuser_token_headers
    )
    assert deleted.status_code == 200

    missing = client.get(f"/api/v1/users/{user_id}", **superuser_token_headers)
    assert missing.status_code == 404


def test_task_endpoint_dispatches_celery(client, monkeypatch):
    captured = {}

    def fake_send_task(name, args=None, **kwargs):
        captured["name"] = name
        captured["args"] = args

    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    response = client.get("/api/v1/task")
    assert response.status_code == 200
    assert response.json() == {"message": "success"}
    assert captured["name"] == "app.tasks.example_task"
    assert captured["args"] == ["Hello World"]


def test_inactive_user_can_login_but_is_denied(client, db):
    User.objects.create(
        email="inactive@example.com",
        hashed_password=get_password_hash("pw123456"),
        is_active=False,
    )
    login = client.post(
        "/api/token",
        {"username": "inactive@example.com", "password": "pw123456"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/v1/users/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert me.status_code == 400
    assert me.json()["detail"] == "Inactive user"

    superuser_route = client.get(
        "/api/v1/users", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert superuser_route.status_code == 400
    assert superuser_route.json()["detail"] == "Inactive user"


def test_non_bearer_scheme_is_ignored(client, db):
    response = client.get(
        "/api/v1/users/me", HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz"
    )
    assert response.status_code == 401


def test_malformed_bearer_header_rejected(client, db):
    only_scheme = client.get("/api/v1/users/me", HTTP_AUTHORIZATION="Bearer")
    assert only_scheme.status_code == 401
    too_many_parts = client.get(
        "/api/v1/users/me", HTTP_AUTHORIZATION="Bearer a b"
    )
    assert too_many_parts.status_code == 401


def test_invalid_token_rejected(client, db):
    response = client.get(
        "/api/v1/users/me", HTTP_AUTHORIZATION="Bearer garbage.token.here"
    )
    assert response.status_code == 401


def test_token_without_subject_rejected(client, db):
    token = create_access_token(data={"permissions": "user"})
    response = client.get(
        "/api/v1/users/me", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert response.status_code == 401


def test_token_for_unknown_user_rejected(client, db):
    token = create_access_token(
        data={"sub": "ghost@nowhere.com", "permissions": "user"}
    )
    response = client.get(
        "/api/v1/users/me", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert response.status_code == 401
