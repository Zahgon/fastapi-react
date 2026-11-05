from django.http import StreamingHttpResponse
from django.urls import Resolver404, get_resolver, resolve
from django.urls.resolvers import URLResolver

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
        if (
            not getattr(response, "streaming", False)
            and "Content-Length" not in response
        ):
            response["Content-Length"] = str(len(response.content))
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

        # Starlette stripped *every* trailing slash (`rstrip("/")`) or added
        # one, and rebuilt the URL from the request scope -- so the redirect
        # keeps the request's host and its query string.
        alternative = path.rstrip("/") if path.endswith("/") else path + "/"
        if not alternative or not _resolves(alternative):
            return response
        query = request.META.get("QUERY_STRING", "")
        if query:
            alternative = f"{alternative}?{query}"

        redirect = StreamingHttpResponse(iter(()), status=307)
        del redirect["Content-Type"]
        # The raw `Host` header, as Starlette's `URL(scope=...)` used it:
        # `build_absolute_uri` would validate it and reject names Starlette
        # served, such as `backend_1:8888`.
        host = request.META.get("HTTP_HOST") or request.META["SERVER_NAME"]
        redirect["Location"] = f"{request.scheme}://{host}{alternative}"
        return redirect


class StarletteMethodResolution:
    """Keep scanning the route table after a method miss, as Starlette's router did.

    Starlette matched on the path *and* the method together: a route whose path
    matched but whose method set did not was passed over, and the scan carried
    on through the remaining routes. Only when none was left did it answer
    **405**. Django's resolver stops at the first pattern whose path matches and
    never reconsiders, so a path two patterns can match answers 405 from the
    first of them even when the second declares the method.

    On a 405 this re-runs the scan and hands the request to the next
    path-matching route that declares the method, which is the route Starlette
    would have reached. The gates of *that* route then decide the answer, so an
    unauthenticated request can come back 401 rather than 405.

    Nothing here names a route, a path or a method: the method set is read off
    each view class, so any pair of overlapping patterns behaves as the original
    did. The 405 is raised in `StarletteDispatchAPIView.initial` before
    authentication and before the body is read, so the passed-over route leaves
    no trace for the second one to inherit.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 405:
            return response
        match = _route_declaring(request.path_info, request.method)
        if match is None:
            return response
        view, args, kwargs = match
        answer = view(request, *args, **kwargs)
        # The handler renders a deferred response inside `_get_response`, which
        # has already run by the time a middleware sees its result.
        if hasattr(answer, "render") and callable(answer.render):
            answer = answer.render()
        return answer


def _route_declaring(path, method):
    """The first path-matching route that declares `method`, or `None`.

    The route that produced the 405 does not declare it, so it is skipped by
    the same test rather than by counting matches.
    """
    wanted = method.lower()
    for view, args, kwargs in _path_matches(path):
        view_class = getattr(view, "cls", None)
        if view_class is None:
            continue
        if wanted in getattr(view_class, "http_method_names", ()) and hasattr(
            view_class, wanted
        ):
            return view, args, kwargs
    return None


def _path_matches(path, patterns=None, args=(), kwargs=None):
    """Every route whose path matches, in declaration order.

    `URLResolver.resolve` returns only the first; this walks the same tree and
    yields all of them, carrying the arguments each level captured.
    """
    if patterns is None:
        patterns = get_resolver().url_patterns
        path = path[1:] if path.startswith("/") else path
    kwargs = kwargs or {}
    for pattern in patterns:
        matched = pattern.pattern.match(path)
        if matched is None:
            continue
        rest, new_args, new_kwargs = matched
        merged = {**kwargs, **new_kwargs}
        if isinstance(pattern, URLResolver):
            yield from _path_matches(
                rest, pattern.url_patterns, args + new_args, merged
            )
        else:
            yield pattern.callback, args + new_args, merged


def _resolves(path):
    try:
        resolve(path)
    except Resolver404:
        return False
    return True
