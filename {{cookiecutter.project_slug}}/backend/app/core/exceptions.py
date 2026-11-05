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
        # it to a single string.
        request = context.get("request") if context else None
        response.data = {"detail": _jsondecode_detail(exc, request)}
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
    "str": ("str type expected", "type_error.str"),
    "bool": ("value could not be parsed to a boolean", "type_error.bool"),
}


def to_pydantic_errors(serializer):
    """Translate `serializer.errors` into pydantic's `detail` list.

    DRF collects field errors in declaration order, which the serializers keep
    identical to the original models', so the list comes out in pydantic's
    order too.
    """
    errors = []
    for name, messages in serializer.errors.items():
        for message in messages:
            code = getattr(message, "code", "invalid")
            msg, type_ = _BY_CODE.get(code, (str(message), "value_error"))
            errors.append({"loc": ["body", name], "msg": msg, "type": type_})
    return errors


#: What FastAPI reported when the request carried no body at all. The endpoint
#: declared a single `user: UserCreate` body parameter, so an absent body made
#: *that one field* missing -- `loc` is `["body"]`, with no field name after it.
#: Only once a body exists does pydantic validate the model and report per-field
#: entries. Read off the running baseline: `POST /api/v1/users` with an empty
#: body, or a JSON `null`, answers one error, not one per declared field.
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


class RequestValidationError(APIException):
    """422 carrying pydantic's error document rather than DRF's."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, errors):
        super().__init__({"detail": errors})


def body_errors(serializer_class, request):
    """Validate the request body; return `(validated_data, errors)`.

    The original validated path and body parameters together and reported all
    of their errors at once, so this returns the errors instead of raising.
    A missing body or a JSON `null` is one error naming the body itself. Any
    other JSON value that is not an object carried none of the model's fields:
    pydantic read it as an object without attributes and reported every
    required field missing.
    """
    data = request.data if raw_body(request) else None
    if data is None:
        return None, list(BODY_REQUIRED)
    if not isinstance(data, dict):
        data = {}
    serializer = serializer_class(data=data)
    if serializer.is_valid():
        return serializer.validated_data, []
    return None, to_pydantic_errors(serializer)


class JSONBodyError(ParseError):
    """A JSON body the decoder rejected, keeping the decoder's own error."""

    def __init__(self, error):
        super().__init__(str(error))
        self.decode_error = error


class UnreadableBody(APIException):
    """A JSON body whose bytes are not text in any JSON encoding.

    FastAPI caught `json.JSONDecodeError` itself and answered every other
    failure to read the body with this 400. Bytes that are not valid UTF-8,
    UTF-16 or UTF-32 fail before JSON parsing starts, so they land here.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "There was an error parsing the body"
    default_code = "body_unreadable"


def _not_a_dict_detail():
    """pydantic's entry for a body it could not read as an object at all."""
    return [
        {
            "loc": ["body"],
            "msg": "value is not a valid dict",
            "type": "type_error.dict",
        }
    ]


def _jsondecode_detail(exc, request):
    """Rebuild pydantic's `value_error.jsondecode` entry for a malformed body."""
    import json

    err = getattr(exc, "decode_error", None)
    if err is None:
        try:
            json.loads(raw_body(request))
        except json.JSONDecodeError as decode_error:
            err = decode_error
        except ValueError:
            # UnicodeDecodeError is a ValueError, and json.loads raises it for
            # bytes that are not text in any JSON encoding. That failure carries
            # no position to report, so it converts here to the entry pydantic
            # used for a body it could not read as an object.
            return _not_a_dict_detail()
    if err is None:
        return _not_a_dict_detail()
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
