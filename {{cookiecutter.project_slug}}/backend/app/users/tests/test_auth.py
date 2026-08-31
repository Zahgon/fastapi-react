from app.core import security


def verify_password_mock(first: str, second: str):
    return True


def test_login(client, test_user, monkeypatch):
    monkeypatch.setattr(security, "verify_password", verify_password_mock)

    response = client.post(
        "/api/token",
        {"username": test_user.email, "password": "nottheactualpass"},
    )
    assert response.status_code == 200


def test_signup(client, db, monkeypatch):
    # NOTE: this mock has the wrong signature on purpose and is patched onto
    # the ``security`` module attribute, whereas ``create_user`` uses a direct
    # import of ``get_password_hash``. The patch therefore has no effect and
    # the real bcrypt hashing runs -- faithfully mirroring the original test.
    def get_password_hash_mock(first: str, second: str):
        return True

    monkeypatch.setattr(security, "get_password_hash", get_password_hash_mock)

    response = client.post(
        "/api/signup",
        {"username": "some@email.com", "password": "randompassword"},
    )
    assert response.status_code == 200


def test_resignup(client, test_user, monkeypatch):
    monkeypatch.setattr(security, "verify_password", verify_password_mock)

    response = client.post(
        "/api/signup",
        {"username": test_user.email, "password": "randompassword"},
    )
    assert response.status_code == 409


def test_wrong_password(client, test_user, test_password, monkeypatch):
    def verify_password_failed_mock(first: str, second: str):
        return False

    monkeypatch.setattr(
        security, "verify_password", verify_password_failed_mock
    )

    response = client.post(
        "/api/token", {"username": test_user.email, "password": "wrong"}
    )
    assert response.status_code == 401


def test_wrong_login(client, test_user, test_password):
    response = client.post(
        "/api/token", {"username": "fakeuser", "password": test_password}
    )
    assert response.status_code == 401
