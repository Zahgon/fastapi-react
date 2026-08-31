"""Three contract details the ported suite never read.

A mutation run found these: the suite is green at 38 tests and 99% coverage and
still did not notice a token that stopped claiming admin, a delete response that
lost its ``id``, or a created user that arrived deactivated. Each test below
pins one of them.
"""

import jwt

from app.core import security
from app.users.models import User


def _claims(token: str) -> dict:
    return jwt.decode(
        token, security.SECRET_KEY, algorithms=[security.ALGORITHM]
    )


def test_token_carries_the_permissions_claim(
    client, db, test_user, test_superuser, test_password, monkeypatch
):
    """The original put ``permissions`` in the JWT and react-admin reads it to
    decide what to render. Every existing test treats the token as opaque, so
    the claim could say anything at all and the suite would still pass."""
    monkeypatch.setattr(security, "verify_password", lambda a, b: True)

    normal = client.post(
        "/api/token", {"username": test_user.email, "password": test_password}
    )
    admin = client.post(
        "/api/token",
        {"username": test_superuser.email, "password": test_password},
    )

    assert _claims(normal.json()["access_token"])["permissions"] == "user"
    assert _claims(admin.json()["access_token"])["permissions"] == "admin"
    assert _claims(admin.json()["access_token"])["sub"] == test_superuser.email


def test_delete_returns_the_user_as_it_was_before_deletion(
    client, db, test_superuser, superuser_token_headers
):
    """`delete_user` answered with the deleted row, id included. Django resets
    the primary key on ``delete()``, so serializing afterwards silently drops
    the ``id`` key -- the output serializer omits ``None`` values."""
    victim = User.objects.create(
        email="deleteme@email.com", hashed_password="x", is_active=True
    )

    response = client.delete(
        f"/api/v1/users/{victim.pk}", **superuser_token_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == victim.pk
    assert body["email"] == "deleteme@email.com"
    assert not User.objects.filter(pk=victim.pk).exists()


def test_created_user_is_active_unless_told_otherwise(
    client, db, test_superuser, superuser_token_headers
):
    """`is_active` defaulted to True on the pydantic model, so a create that
    omits it produces a usable account. A default of False would deactivate
    every user created through the admin surface."""
    response = client.post(
        "/api/v1/users",
        {"email": "defaulted@email.com", "password": "s3cret-pass"},
        format="json",
        **superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True
    assert User.objects.get(email="defaulted@email.com").is_active is True


# --- the six differences a side-by-side differential against the running
# --- original found, and the shapes it proved they should have.


def test_the_four_generated_doc_endpoints_are_served(client, db):
    """FastAPI created `/api`, `/api/docs`, `/redoc` and `/docs/oauth2-redirect`
    for free. Django creates none of them, and the port had dropped all four."""
    schema = client.get("/api")
    assert schema.status_code == 200
    assert schema["Content-Type"].startswith("application/json")
    assert "openapi" in schema.json()

    for path in ("/api/docs", "/redoc", "/docs/oauth2-redirect"):
        assert client.get(path).status_code == 200, path


def test_non_numeric_id_is_rejected_by_the_validation_layer(
    client, db, test_superuser, superuser_token_headers
):
    """`user_id: int` made this a 422 from the application. `<int:pk>` would
    make it an HTML 404 from the URL resolver, before any code runs."""
    response = client.get("/api/v1/users/abc", **superuser_token_headers)

    assert response.status_code == 422
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {
        "detail": [
            {
                "loc": ["path", "user_id"],
                "msg": "value is not a valid integer",
                "type": "type_error.integer",
            }
        ]
    }


def test_negative_id_routes_and_then_reports_not_found(
    client, db, test_superuser, superuser_token_headers
):
    """`-1` is a valid integer, so it routed and the lookup answered."""
    response = client.get("/api/v1/users/-1", **superuser_token_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_unrouted_path_answers_json(client, db):
    """The original had no HTML surface at all."""
    response = client.get("/no-such-endpoint")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def test_create_validation_failure_is_422_not_400(
    client, db, test_superuser, superuser_token_headers
):
    """The 422 rule applies to every endpoint, not only login and signup."""
    response = client.post(
        "/api/v1/users",
        {"password": "s3cret-pass"},
        format="json",
        **superuser_token_headers,
    )

    assert response.status_code == 422


def test_duplicate_signup_advertises_bearer(client, db):
    """The original raised its 409 with headers={"WWW-Authenticate": "Bearer"}."""
    creds = {"username": "dupe@email.com", "password": "s3cret-pass"}
    assert client.post("/api/signup", creds).status_code == 200

    conflict = client.post("/api/signup", creds)

    assert conflict.status_code == 409
    assert conflict["WWW-Authenticate"] == "Bearer"


def test_user_payload_key_order_matches_the_original(
    client, db, test_superuser, superuser_token_headers
):
    """pydantic emitted `UserBase`'s fields first and `id` last, because
    `User(UserBase)` is what adds it. Key order is part of what a client sees.
    """
    response = client.get(
        f"/api/v1/users/{test_superuser.pk}", **superuser_token_headers
    )

    assert response.status_code == 200
    assert list(response.json().keys()) == [
        "email",
        "is_active",
        "is_superuser",
        "id",
    ]


def test_unauthenticated_detail_matches_the_original(client, db):
    """`detail` is the only field in either body, so its wording is what a
    client actually reads. DRF's stock sentence is not the original's."""
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_unauthorized_detail_matches_the_original(
    client, db, test_user, user_token_headers
):
    response = client.get("/api/v1/users", **user_token_headers)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "The user doesn't have enough privileges"
    }


def test_email_accepts_any_string_as_the_original_did(
    client, db, test_superuser, superuser_token_headers
):
    """`email: str` on a pydantic model with a SQLAlchemy `Column(String)`
    accepted and stored anything. `EmailField` rejects `not-an-email` and even
    `a@b.c`, which narrows the contract instead of porting it."""
    response = client.post(
        "/api/v1/users",
        {"email": "not-an-email", "password": "s3cret-pass"},
        format="json",
        **superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json()["email"] == "not-an-email"


def test_validation_errors_use_pydantics_document(
    client, db, test_superuser, superuser_token_headers
):
    """Both sides answer 422, but the shape is what a client parses. These
    documents were read off the running original, not guessed."""
    both_missing = client.post(
        "/api/v1/users", {}, format="json", **superuser_token_headers
    )
    assert both_missing.status_code == 422
    assert both_missing.json() == {
        "detail": [
            {
                "loc": ["body", "email"],
                "msg": "field required",
                "type": "value_error.missing",
            },
            {
                "loc": ["body", "password"],
                "msg": "field required",
                "type": "value_error.missing",
            },
        ]
    }

    null_email = client.post(
        "/api/v1/users",
        {"email": None, "password": "s3cret-pass"},
        format="json",
        **superuser_token_headers,
    )
    assert null_email.json() == {
        "detail": [
            {
                "loc": ["body", "email"],
                "msg": "none is not an allowed value",
                "type": "type_error.none.not_allowed",
            },
        ]
    }

    bad_boolean = client.post(
        "/api/v1/users",
        {"email": "x@y.z", "password": "s3cret-pass", "is_active": "maybe"},
        format="json",
        **superuser_token_headers,
    )
    assert bad_boolean.json() == {
        "detail": [
            {
                "loc": ["body", "is_active"],
                "msg": "value could not be parsed to a boolean",
                "type": "type_error.bool",
            },
        ]
    }


def test_blank_strings_are_accepted_as_the_original_did(
    client, db, test_superuser, superuser_token_headers
):
    """`email: str` accepted an empty string and stored it. DRF's `CharField`
    refuses blanks by default, which is validation the original never had."""
    response = client.post(
        "/api/v1/users",
        {"email": "", "password": "s3cret-pass"},
        format="json",
        **superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json()["email"] == ""


def test_malformed_json_uses_pydantics_decode_document(
    client, db, test_superuser, superuser_token_headers
):
    """pydantic reported a bad body as a `value_error.jsondecode` entry with the
    decoder's own position and context. DRF collapses it to one string."""
    response = client.post(
        "/api/v1/users",
        '{"email":',
        content_type="application/json",
        **superuser_token_headers,
    )

    assert response.status_code == 422
    entry = response.json()["detail"][0]
    assert entry["type"] == "value_error.jsondecode"
    assert entry["loc"] == ["body", 9]
    assert entry["ctx"]["msg"] == "Expecting value"
    assert entry["ctx"]["pos"] == 9


def test_unhandled_errors_answer_plain_text(db, monkeypatch):
    """Starlette's `ServerErrorMiddleware` returns the bare string
    ``Internal Server Error`` as `text/plain`. Django returns an HTML page, and
    `GET /api/v1/task` reaches this path whenever the Celery broker is
    unreachable.

    The failure is INJECTED rather than waited for. This test used to rely on
    the broker simply not being there, which is true of a bare `pytest` run and
    false under the project's own docker-compose -- where `redis` is a declared
    service. So it asserted `500` in the environment where the evidence was
    recorded and failed with `200` in the environment the project documents,
    which makes it a statement about the machine rather than about the port.
    Patching `send_task` to raise pins the behaviour under test -- what Django
    returns for an exception no handler catches -- in both.

    The client is built here rather than taken from the fixture because it has
    to be told not to re-raise: the point of the test is the response Django
    produces for an unhandled exception, not the exception itself.
    """
    from rest_framework.test import APIClient

    from app import views

    def _broker_is_down(*args, **kwargs):
        raise OSError("Errno 111 Connection refused")

    monkeypatch.setattr(views.celery_app, "send_task", _broker_is_down)

    response = APIClient(raise_request_exception=False).get("/api/v1/task")

    assert response.status_code == 500
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert response.content == b"Internal Server Error"


def test_schema_document_matches_the_originals_shape(client, db):
    """FastAPI derived `/api` from its route table and `response_model=`
    declarations. `drf-spectacular` reads plain `APIView`s and infers nothing,
    so every operation is annotated by hand. These are the original's own
    values, read from its running `/api`."""
    schema = client.get("/api").json()

    assert sorted(schema["paths"]) == [
        "/api/signup",
        "/api/token",
        "/api/v1",
        "/api/v1/task",
        "/api/v1/users",
        "/api/v1/users/me",
        "/api/v1/users/{user_id}",
    ]
    assert sorted(schema["paths"]["/api/v1/users/{user_id}"]) == [
        "delete",
        "get",
        "put",
    ]
    assert schema["components"]["securitySchemes"] == {
        "OAuth2PasswordBearer": {
            "type": "oauth2",
            "flows": {"password": {"scopes": {}, "tokenUrl": "/api/token"}},
        }
    }


def test_string_columns_are_unbounded_varchar():
    """The baseline's `Column(String)` emitted an unbounded `varchar`; a
    `max_length` would reject values the original stored.

    This asserts the column type rather than the behaviour on purpose: the
    suite runs on SQLite, which does not enforce `varchar(n)` at all, so a
    length limit would be invisible to every request-level test and only bite
    against the PostgreSQL the application actually deploys on.
    """
    from django.db import connection

    from app.users.models import User

    for name in ("email", "first_name", "last_name", "hashed_password"):
        field = User._meta.get_field(name)
        assert field.db_type(connection) == "varchar", name
        assert getattr(field, "max_length", None) is None, name


def test_no_allow_header_on_any_response(
    client, db, test_superuser, superuser_token_headers
):
    """Starlette sent no `Allow` header, on any status. DRF sets one on every
    response. RFC 7231 says a 405 `MUST` carry it, so the original was wrong --
    and porting the wrongness is what the brief asks for."""
    ok = client.get("/api/v1")
    assert ok.status_code == 200
    assert not ok.has_header("Allow")

    not_allowed = client.delete("/api/v1")
    assert not_allowed.status_code == 405
    assert not not_allowed.has_header("Allow")

    listing = client.get("/api/v1/users", **superuser_token_headers)
    assert listing.status_code == 200
    assert not listing.has_header("Allow")

    # `drf-spectacular`'s Swagger view sets a COOP header; Starlette set none.
    docs = client.get("/api/docs")
    assert docs.status_code == 200
    assert not docs.has_header("Cross-Origin-Opener-Policy")


def test_method_is_resolved_before_authentication(client, db):
    """Starlette answered 405 without running the route's dependencies, so an
    unauthenticated request with an unsupported method was a 405, not a 401.
    DRF authenticates first and would answer 401."""
    response = client.patch("/api/v1/users")

    assert response.status_code == 405
    assert not response.has_header("WWW-Authenticate")


def test_method_not_allowed_wording_matches(client, db):
    """Starlette said `Method Not Allowed`; DRF names the method."""
    response = client.delete("/api/v1")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}


# --- Six more, from the 73-probe differential -----------------------------
#
# The 43-probe set never sent HEAD, OPTIONS, a form-encoded body, a partial
# PUT, or a path with a trailing slash. Widening it to 73 found six behaviours
# that had shipped wrong, each verified against the running FastAPI baseline.


def test_head_is_method_not_allowed(client):
    """`APIRoute` records only the methods the decorator named. Unlike
    Starlette's plain `Route` it does not add HEAD alongside GET, so the
    original answered 405 -- while Django's `View.setup` maps HEAD onto `get`
    and answered 200 with the resource."""
    response = client.head("/api/v1")
    assert response.status_code == 405


def test_options_is_method_not_allowed(client):
    """Nothing installed a CORS middleware, so OPTIONS had no handler and the
    original answered 405. DRF's `APIView.options` answered 200 with a metadata
    document describing the view -- and on `/api/v1/users` it answered 401,
    because the permission check ran first."""
    response = client.options("/api/v1")
    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}

    guarded = client.options("/api/v1/users")
    assert guarded.status_code == 405


def test_users_me_falls_through_to_the_id_route(client):
    """Starlette scanned its routes for a *method* match: `/users/me` is
    GET-only, so `PUT /api/v1/users/me` carried on to `/users/{user_id}` and
    was answered by its superuser dependency with 401. Django stops at the
    first path match, which made it a 405."""
    for method in (client.put, client.delete):
        response = method("/api/v1/users/me")
        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}
        assert response["WWW-Authenticate"] == "Bearer"


def test_trailing_slash_redirects(client):
    """Starlette's router carried `redirect_slashes=True` and answered a 307
    with an absolute Location. Django had no equivalent and answered 404."""
    response = client.get("/api/v1/")
    assert response.status_code == 307
    assert response["Location"].endswith("/api/v1")
    # `CommonMiddleware`'s APPEND_SLASH would have made this a 301, which a
    # client is entitled to cache permanently.
    assert response.status_code != 301


def test_form_encoded_body_is_no_body_at_all(client, superuser_token_headers):
    """FastAPI parsed a body as JSON only when the content type said JSON;
    anything else reached the pydantic model as raw bytes, which have no
    `.get`, so every field came back `field required`. DRF's default
    `FormParser` accepted the same request and created the account."""
    response = client.post(
        "/api/v1/users",
        "email=form@example.com&password=pw123456",
        content_type="application/x-www-form-urlencoded",
        **superuser_token_headers,
    )
    assert response.status_code == 422
    assert [e["loc"] for e in response.json()["detail"]] == [
        ["body", "email"],
        ["body", "password"],
    ]
    assert not User.objects.filter(email="form@example.com").exists()


def test_put_without_email_is_rejected(
    client, test_user, superuser_token_headers
):
    """`UserEdit` inherits `email: str` from `UserBase` with no default, so
    pydantic required it on every PUT. An edit that omitted it -- or an empty
    body -- was a 422, not a partial update."""
    for payload in ({"first_name": "Only"}, {}):
        response = client.put(
            f"/api/v1/users/{test_user.id}",
            payload,
            format="json",
            **superuser_token_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"] == [
            {
                "loc": ["body", "email"],
                "msg": "field required",
                "type": "value_error.missing",
            }
        ]
    test_user.refresh_from_db()
    assert test_user.first_name is None


def test_content_range_is_emitted_after_the_body_headers(
    client, superuser_token_headers
):
    """FastAPI assembled headers in two passes: the JSON response and its body
    headers first, then whatever the handler set on the injected `response`
    parameter. `Content-Range` is set that way, so it arrives last."""
    response = client.get("/api/v1/users", **superuser_token_headers)
    names = [name.lower() for name, _ in response.items()]
    assert names[-3:] == ["content-length", "content-type", "content-range"]


def test_documentation_routes_allow_only_get_and_head(client):
    """FastAPI mounted these four with `add_route`, a plain Starlette `Route`:
    it adds HEAD alongside GET but nothing else, so every other method was a
    405. As `APIView` subclasses they answered OPTIONS with a metadata
    document instead -- and `/api/docs` answered **500**, because building that
    document crashed the Swagger view's renderer."""
    for path in ("/api", "/api/docs", "/redoc", "/docs/oauth2-redirect"):
        options = client.options(path)
        assert options.status_code == 405, path
        assert options.json() == {"detail": "Method Not Allowed"}
        assert options["Content-Type"] == "application/json"

        # HEAD, by contrast, is a 200 here -- the opposite of `/api/v1`.
        assert client.head("/api").status_code == 200


def test_redirect_headers_are_lowercase(client):
    """Starlette lowercased every header name on the wire. The redirect is a
    streaming response, which the header middleware was skipping entirely, so
    it went out as `Location` and `Transfer-Encoding`."""
    response = client.get("/api/v1/")
    assert response.status_code == 307
    assert [name for name, _ in response.items()] == ["location"]


def test_absent_body_is_one_error_naming_the_body_itself(
    client, test_user, superuser_token_headers
):
    """A request with no body at all reported **one** error, not one per field.

    The endpoint declared a single `user: UserCreate` body parameter, so an
    absent body made that one field missing -- `loc` is `["body"]`, with no
    field name after it. Only once a body exists does pydantic validate the
    model and report per-field entries. `{}` is a two-byte body and does not
    exercise this; the differential is what found it, and this test originally
    asserted the per-field shape because it was reasoned from FastAPI's source
    instead of read off the running original."""
    body_required = [
        {
            "loc": ["body"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]
    created = client.post(
        "/api/v1/users",
        "",
        content_type="application/json",
        **superuser_token_headers,
    )
    assert created.status_code == 422
    assert created.json()["detail"] == body_required

    edited = client.put(
        f"/api/v1/users/{test_user.id}",
        "",
        content_type="application/json",
        **superuser_token_headers,
    )
    assert edited.status_code == 422
    assert edited.json()["detail"] == body_required

    # A body that exists but is empty still reports per-field, as before.
    braces = client.post(
        "/api/v1/users",
        {},
        format="json",
        **superuser_token_headers,
    )
    assert [e["loc"] for e in braces.json()["detail"]] == [
        ["body", "email"],
        ["body", "password"],
    ]
