import json

from rest_framework.parsers import BaseParser

from app.core.exceptions import JSONBodyError, UnreadableBody


def _is_json(media_type):
    """FastAPI's own test: `application/json`, or any `application/*+json`."""
    main, _, rest = (media_type or "").partition("/")
    subtype = rest.split(";")[0].strip().lower()
    return main.strip().lower() == "application" and (
        subtype == "json" or subtype.endswith("+json")
    )


class StarletteBodyParser(BaseParser):
    """Decode a request body the way FastAPI did, not the way DRF does.

    FastAPI looked at the content type before it looked at the body. It called
    `request.json()` only when the media type was `application/json` or carried
    a `+json` suffix; for anything else it handed the *raw bytes* to the
    pydantic model. Bytes have no `.get`, so every declared field came back
    `field required` and the request was a 422 -- a form-encoded body was not a
    parse error, it was **no body at all**.

    DRF installs `FormParser` and `MultiPartParser` by default, so the same
    request parsed cleanly and the handler ran. Verified against the running
    baseline: `POST /api/v1/users` with `email=...&password=...` sent as a form
    answers 422 with `email` and `password` both missing, while the port
    answered 200 and created the account.
    """

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        body = stream.read()
        # Reading the stream consumes it, and Django then refuses
        # `request.body` outright. The 422 handler needs those bytes to rebuild
        # pydantic's `value_error.jsondecode` entry, so keep them here.
        request = (parser_context or {}).get("request")
        if request is not None:
            request.starlette_raw_body = body
        # `if body_bytes:` in FastAPI -- an empty body leaves the model unset
        # rather than raising, which is why an empty PUT was a 422 about the
        # missing field and not a decode error.
        if not body:
            return {}
        # No content type at all is not JSON either: FastAPI 0.65 parsed JSON
        # only when the header named a JSON media type.
        if not _is_json(media_type):
            return {}
        # `json.loads` on the raw bytes, as Starlette's `request.json()` did:
        # it detects UTF-8, UTF-16 and UTF-32 by itself. Bytes that are none
        # of those fail before any JSON is read, and FastAPI answered that
        # with a 400 rather than its JSON-decode 422.
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise JSONBodyError(exc)
        except ValueError as exc:
            raise UnreadableBody() from exc
