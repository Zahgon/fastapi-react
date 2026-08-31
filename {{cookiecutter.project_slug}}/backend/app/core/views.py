from rest_framework.exceptions import MethodNotAllowed
from rest_framework.views import APIView


class StarletteDispatchAPIView(APIView):
    """An `APIView` that resolves the method before it authenticates.

    Starlette's router matched the path, found no handler for the method and
    answered **405** without ever running the route's dependencies -- so
    `PATCH /api/v1/users` with no credentials was a 405, not a 401.

    DRF's `dispatch` calls `initial()` -- authentication and permissions --
    *before* it looks the handler up, so the same request answers 401. Checking
    the handler first restores the original ordering. Authentication still runs
    for every method the view actually implements.
    """

    #: Django maps `HEAD` onto `get` in `View.setup`, and DRF answers `OPTIONS`
    #: with a metadata document. FastAPI did neither: `APIRoute` records only
    #: the methods the decorator named -- unlike Starlette's plain `Route` it
    #: does not add `HEAD` alongside `GET` -- and nothing installed a CORS
    #: middleware, so `OPTIONS` had no handler either. Both answered 405.
    #: Verified on the running baseline: `HEAD /api/v1` and `OPTIONS /api/v1`
    #: are each `405 Method Not Allowed` with `{"detail": "Method Not Allowed"}`.
    http_method_names = ["get", "post", "put", "patch", "delete"]

    def initial(self, request, *args, **kwargs):
        method = request.method.lower()
        if method not in self.http_method_names or not hasattr(self, method):
            raise MethodNotAllowed(request.method)
        return super().initial(request, *args, **kwargs)
