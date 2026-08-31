from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    MethodNotAllowed,
    NotAuthenticated,
    ParseError,
    PermissionDenied,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

# The wording the original sent. DRF has its own stock sentences for both, and
# they are what a client actually reads: `detail` is the only field in either
# body, so a consumer matching on it sees a different service.
FASTAPI_DETAIL = {
    NotAuthenticated: "Not authenticated",
    PermissionDenied: "The user doesn't have enough privileges",
    MethodNotAllowed: "Method Not Allowed",
}


def exception_handler(exc, context):
    """Answer request-validation errors with 422, the way FastAPI did.

    Django REST Framework answers `ValidationError` and `ParseError` with 400.
    FastAPI/pydantic answered both with `422 Unprocessable Entity`, and the
    login and signup endpoints already reproduce that by hand. Registering this
    handler extends the same rule to every other endpoint -- `POST /users` with
    a missing `email` was still answering 400.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return response
    if isinstance(exc, (ValidationError, ParseError)):
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    if isinstance(exc, ParseError):
        # pydantic reported a malformed body as a `value_error.jsondecode`
        # entry carrying the decoder's own position and context. DRF collapses
        # it to a single string. Re-run the decode to recover the detail.
        request = context.get("request") if context else None
        response.data = {"detail": _jsondecode_detail(request)}
        return response
    for exc_type, detail in FASTAPI_DETAIL.items():
        if type(exc) is exc_type:
            response.data = {"detail": detail}
            break
    return response


# --- pydantic's validation-error document -------------------------------
#
# FastAPI answered a bad body with pydantic's error list; DRF answers with a
# map of field -> messages. Both are 422 now, but the *shape* is what a client
# parses, and the login and signup views already hand-build the pydantic form.
# This produces the same document for the serializer-driven endpoints.
#
# The (msg, type) pairs were read off the running original, not guessed.

_BY_CODE = {
    "required": ("field required", "value_error.missing"),
    "null": ("none is not an allowed value", "type_error.none.not_allowed"),
}


def to_pydantic_errors(serializer):
    """Translate `serializer.errors` into pydantic's `detail` list."""
    from rest_framework import serializers as drf

    errors = []
    for name, messages in serializer.errors.items():
        field = serializer.fields.get(name)
        for message in messages:
            code = getattr(message, "code", "invalid")
            if code in _BY_CODE:
                msg, type_ = _BY_CODE[code]
            elif isinstance(field, drf.BooleanField):
                msg, type_ = (
                    "value could not be parsed to a boolean",
                    "type_error.bool",
                )
            else:
                msg, type_ = str(message), "value_error"
            errors.append({"loc": ["body", name], "msg": msg, "type": type_})
    return errors


#: What FastAPI reported when the request carried no body at all. The endpoint
#: declared a single `user: UserCreate` body parameter, so an absent body made
#: *that one field* missing -- `loc` is `["body"]`, with no field name after it.
#: Only once a body exists does pydantic validate the model and report per-field
#: entries. Read off the running baseline: `POST /api/v1/users` with an empty
#: body answers one error, not one per declared field.
BODY_REQUIRED = [
    {"loc": ["body"], "msg": "field required", "type": "value_error.missing"}
]


def raw_body(request):
    """The request body, whether or not a parser has consumed the stream."""
    if request is None:
        return b""
    raw = getattr(request, "starlette_raw_body", None)
    if raw is None:
        # No parser ran -- DRF skips them all when `CONTENT_LENGTH` is 0 --
        # so the stream is still intact.
        raw = getattr(request, "body", b"")
    return raw or b""


class PydanticValidationError(APIException):
    """422 carrying pydantic's error document rather than DRF's."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, serializer, body_absent=False):
        detail = (
            BODY_REQUIRED if body_absent else to_pydantic_errors(serializer)
        )
        super().__init__({"detail": detail})


def validated(serializer, request=None):
    """Run a serializer, raising the original's error document on failure."""
    if not serializer.is_valid():
        raise PydanticValidationError(
            serializer, body_absent=not raw_body(request)
        )
    return serializer.validated_data


def _jsondecode_detail(request):
    """Rebuild pydantic's `value_error.jsondecode` entry for a malformed body."""
    import json

    raw = raw_body(request)
    text = raw.decode("utf-8", "replace")
    try:
        json.loads(text)
    except json.JSONDecodeError as err:
        return [
            {
                "loc": ["body", err.pos],
                "msg": str(err),
                "type": "value_error.jsondecode",
                "ctx": {
                    "msg": err.msg,
                    "doc": err.doc,
                    "pos": err.pos,
                    "lineno": err.lineno,
                    "colno": err.colno,
                },
            }
        ]
    return [
        {
            "loc": ["body"],
            "msg": "value is not a valid dict",
            "type": "type_error.dict",
        }
    ]
