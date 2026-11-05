"""Credential-field validation parity with FastAPI's OAuth2PasswordRequestForm.

The original endpoints took ``form_data: OAuth2PasswordRequestForm = Depends()``,
so a body missing ``username`` or ``password`` was rejected by the framework with
a 422 before the handler ran. Empty strings, by contrast, satisfied the form
model and were passed through to the handler.
"""

import pytest

MISSING_USERNAME = {
    "loc": ["body", "username"],
    "msg": "field required",
    "type": "value_error.missing",
}
MISSING_PASSWORD = {
    "loc": ["body", "password"],
    "msg": "field required",
    "type": "value_error.missing",
}


@pytest.mark.parametrize("url", ["/api/token", "/api/signup"])
def test_empty_body_reports_both_missing_fields(client, db, url):
    response = client.post(url, {})

    assert response.status_code == 422
    assert response.json() == {"detail": [MISSING_USERNAME, MISSING_PASSWORD]}


@pytest.mark.parametrize("url", ["/api/token", "/api/signup"])
def test_missing_username_is_rejected(client, db, url):
    response = client.post(url, {"password": "s3cret-pass"})

    assert response.status_code == 422
    assert response.json() == {"detail": [MISSING_USERNAME]}


@pytest.mark.parametrize("url", ["/api/token", "/api/signup"])
def test_missing_password_is_rejected(client, db, url):
    response = client.post(url, {"username": "nobody@example.com"})

    assert response.status_code == 422
    assert response.json() == {"detail": [MISSING_PASSWORD]}


@pytest.mark.parametrize("url", ["/api/token", "/api/signup"])
def test_a_json_body_carries_no_credentials_at_all(client, db, url):
    """A JSON body is not a form body, and these two endpoints only ever read
    a form.

    `OAuth2PasswordRequestForm` bound `username` and `password` from
    `application/x-www-form-urlencoded`. A JSON request therefore supplied
    *neither* field, whatever it happened to contain, and both were reported
    missing. An earlier revision of this test asserted that only `username` was
    missing -- which quietly documented a widened contract, because reading the
    body through `request.data` made the endpoints accept JSON. A side-by-side
    differential against the running original showed a JSON signup creating an
    account the original refused with 422.
    """
    response = client.post(url, {"password": "s3cret-pass"}, format="json")

    assert response.status_code == 422
    assert response.json() == {"detail": [MISSING_USERNAME, MISSING_PASSWORD]}


@pytest.mark.parametrize("url", ["/api/token", "/api/signup"])
def test_a_complete_json_body_is_still_refused(client, db, url):
    """The case that matters: valid-looking credentials sent as JSON must not
    authenticate or create an account."""
    response = client.post(
        url,
        {"username": "json@email.com", "password": "s3cret-pass"},
        format="json",
    )

    assert response.status_code == 422
    assert response.json() == {"detail": [MISSING_USERNAME, MISSING_PASSWORD]}


def test_blank_credentials_still_reach_the_handler(client, db):
    """Empty strings are present values, so they authenticate (and fail) as
    before rather than being turned away by validation."""
    login = client.post("/api/token", {"username": "", "password": ""})

    assert login.status_code == 401
    assert login.json() == {"detail": "Incorrect username or password"}

    signup = client.post("/api/signup", {"username": "", "password": ""})

    assert signup.status_code == 200
    assert signup.json()["token_type"] == "bearer"
