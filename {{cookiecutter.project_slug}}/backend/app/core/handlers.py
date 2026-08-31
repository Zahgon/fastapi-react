from django.http import HttpResponse, JsonResponse


def not_found(request, exception=None):
    """Answer an unrouted path with JSON, the way Starlette did.

    Django's default 404 is an HTML page. The original application had no HTML
    surface at all: every response it could produce, this one included, was
    `application/json` with a `detail` key.
    """
    return JsonResponse({"detail": "Not Found"}, status=404)


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
