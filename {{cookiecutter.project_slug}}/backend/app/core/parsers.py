import json

from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser


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
        if media_type and not _is_json(media_type):
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ParseError(str(exc))
