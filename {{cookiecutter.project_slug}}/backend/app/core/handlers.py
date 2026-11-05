import json

from django.http import HttpResponse


def starlette_json(data, status=200):
    """A JSON response serialised the way Starlette's `JSONResponse` was.

    Compact separators and raw UTF-8: Django's `JsonResponse` writes `", "`
    and `": "` and escapes every non-ASCII character, so the same document
    came out with different bytes and a different `content-length`. DRF's
    `JSONRenderer` already matches; this covers the plain Django views.
    """
    return HttpResponse(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        content_type="application/json",
        status=status,
    )


def not_found(request, exception=None):
    """Answer an unrouted path with JSON, the way Starlette did.

    Django's default 404 is an HTML page. The original application had no HTML
    surface at all: every response it could produce, this one included, was
    `application/json` with a `detail` key.
    """
    return starlette_json({"detail": "Not Found"}, status=404)


def server_error(request):
    """Answer an unhandled exception the way Starlette did.

    Starlette's `ServerErrorMiddleware` returns the bare string
    ``Internal Server Error`` as ``text/plain``. Django returns an HTML page.
    The status is 500 either way, but the body and the content type are not.
    """
    return HttpResponse(
        "Internal Server Error",
        content_type="text/plain; charset=utf-8",
        status=500,
    )
