from django.http import StreamingHttpResponse
from django.urls import Resolver404, resolve

#: Emitted last, in this order -- see `_starlette_order`.
TRAILING = ("content-length", "content-type", "content-range")


class StarletteResponseHeaders:
    """Strip response headers the original never sent.

    Django REST Framework sets `Allow` on *all* responses, not only on a 405.
    Starlette sent it on none of them -- including its own 405, where RFC 7231
    says a response `MUST` generate one. That is a defect in the original, and
    the brief says port the wrongness rather than repair it, so the header is
    removed here instead of being made conditional.

    Verified against the running baseline: `DELETE /api/v1` answers
    `405 Method Not Allowed` with no `Allow` header, and `GET /api/v1` answers
    `200` with none either.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    #: Headers Starlette never emitted. `Allow` is DRF's; the COOP header comes
    #: from `drf-spectacular`'s Swagger view, which decorates itself with it.
    STRIP = ("Allow", "Cross-Origin-Opener-Policy")

    def __call__(self, request):
        response = self.get_response(request)
        for header in self.STRIP:
            if header in response:
                del response[header]
        self._starlette_order(response)
        return response

    @staticmethod
    def _starlette_order(response):
        """Emit the header block the way Starlette did.

        Starlette lowercases every header name and appends `content-length`
        then `content-type` after whatever the application set. Django
        title-cases its names and emits `Content-Type` before `Content-Length`.
        Both are served here by the same uvicorn, so the sequence and the
        capitalisation on the wire are the application's doing, not the
        server's -- and a client that reads raw bytes sees the difference.

        `content-range` comes *after* both, because FastAPI assembled the
        header block in two passes: `serialize_response` built the JSON
        response and its body headers first, then extended it with whatever the
        handler had set on the injected `response: Response` parameter -- and
        `users_list` sets `Content-Range` that way. So the baseline sends
        `content-length, content-type, content-range`, not the other order.
        """
        items = list(response.items())
        if getattr(response, "streaming", False):
            # A streaming response has no body headers to move, but its names
            # still arrive title-cased. The slash redirect is one of these, and
            # the baseline sends `location`, not `Location`.
            for name, value in items:
                del response[name]
            for name, value in items:
                response[name.lower()] = value
            return
        trailing, leading = {}, []
        for name, value in items:
            low = name.lower()
            if low in TRAILING:
                trailing[low] = value
            else:
                leading.append((low, value))
        for name, _ in items:
            del response[name]
        for name, value in leading:
            response[name] = value
        for name in TRAILING:
            if name in trailing:
                response[name] = trailing[name]


class StarletteSlashRedirect:
    """Redirect between the slashed and unslashed spelling of a path.

    Starlette's router carries `redirect_slashes=True`: when no route matched,
    it retried the path with the trailing slash toggled, and if *that* matched
    it answered `307 Temporary Redirect` with an absolute `Location`. So
    `GET /api/v1/` was a redirect to `http://host/api/v1`, and the client
    followed it and got the resource.

    Django has no equivalent. `CommonMiddleware`'s `APPEND_SLASH` only ever
    adds a slash, only for safe methods, and answers `301` -- a permanent
    redirect, which a client may cache forever. It is disabled in the settings
    and this runs instead, in both directions and at the original's status.

    The body is deliberately a stream carrying nothing: the baseline's redirect
    is chunked with neither `content-length` nor `content-type`, because it is
    generated inside the router and re-emitted by Starlette's HTTP middleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 404:
            return response

        path = request.path_info
        if path == "/" or _resolves(path):
            # A 404 raised *by* a matched route -- `User not found` -- is the
            # application's answer, not a routing miss, and must not become a
            # redirect to a path that only differs by a slash.
            return response

        alternative = path[:-1] if path.endswith("/") else path + "/"
        if not alternative or not _resolves(alternative):
            return response

        redirect = StreamingHttpResponse(iter(()), status=307)
        del redirect["Content-Type"]
        redirect["Location"] = request.build_absolute_uri(alternative)
        return redirect


def _resolves(path):
    try:
        resolve(path)
    except Resolver404:
        return False
    return True
