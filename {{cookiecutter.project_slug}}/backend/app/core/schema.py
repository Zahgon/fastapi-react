import functools

from django.http import HttpResponse, JsonResponse
from drf_spectacular.renderers import OpenApiJsonRenderer
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.views import SpectacularJSONAPIView


class SchemaJSONRenderer(OpenApiJsonRenderer):
    """Serve the OpenAPI document as plain ``application/json``.

    ``drf-spectacular`` labels its JSON schema ``application/vnd.oai.openapi+json``
    and content-negotiates to YAML by default. FastAPI served the document at
    ``/api`` as ``application/json``, and a client that checks the header sees a
    different service otherwise.
    """

    media_type = "application/json"


class SchemaView(SpectacularJSONAPIView):
    """``GET /api`` — the schema endpoint FastAPI generated for free.

    Also drops ``Content-Disposition``: ``drf-spectacular`` labels the document
    as a named file to show inline, which invites a browser to download it.
    FastAPI sent an ordinary JSON response.
    """

    renderer_classes = [SchemaJSONRenderer]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.headers.pop("Content-Disposition", None)
        return response


OAUTH2_REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head><title>Swagger UI: OAuth2 Redirect</title></head>
<body>
<script>
'use strict';
function run () {
    var oauth2 = window.opener.swaggerUIRedirectOauth2;
    var sentState = oauth2.state;
    var redirectUrl = oauth2.redirectUrl;
    var isValid, qp, arr;

    if (/code|token|error/.test(window.location.hash)) {
        qp = window.location.hash.substring(1);
    } else {
        qp = location.search.substring(1);
    }

    arr = qp.split("&");
    arr.forEach(function (v, i, _arr) { _arr[i] = '"' + v.replace('=', '":"') + '"'; });
    qp = qp ? JSON.parse('{' + arr.join() + '}',
            function (key, value) { return key === "" ? value : decodeURIComponent(value); }
        ) : {};

    isValid = qp.state === sentState;

    if ((oauth2.auth.schema.get("flow") === "accessCode" ||
         oauth2.auth.schema.get("flow") === "authorizationCode" ||
         oauth2.auth.schema.get("flow") === "authorization_code") && !oauth2.auth.code) {
        if (!isValid) {
            oauth2.errCb({level: "warning", message: "Authorization may be unsafe"});
        }
        if (qp.code) {
            delete oauth2.state;
            oauth2.auth.code = qp.code;
            oauth2.callback({auth: oauth2.auth, redirectUrl: redirectUrl});
        } else {
            oauth2.errCb({level: "error", message: "Authorization failed: no accessCode received"});
        }
    } else {
        oauth2.callback({auth: oauth2.auth, token: qp, isValid: isValid, redirectUrl: redirectUrl});
    }
    window.close();
}

if (document.readyState !== 'loading') { run(); }
else { document.addEventListener('DOMContentLoaded', function () { run(); }); }
</script>
</body>
</html>
"""


def oauth2_redirect(request):
    """``GET /docs/oauth2-redirect`` — served inline, with 200.

    Starlette answered this path with the Swagger OAuth2 redirect document
    directly. ``drf-spectacular``'s equivalent view answers **302** to a static
    asset instead, which is a different status and a different content type on
    the wire, so the page is returned here rather than redirected to.
    """
    # Starlette sent the charset; Django omits it unless asked.
    return HttpResponse(
        OAUTH2_REDIRECT_HTML, content_type="text/html; charset=utf-8"
    )


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Teach the schema generator about the hand-written JWT authenticator.

    Without this, `drf-spectacular` reports `could not resolve authenticator`
    for every protected view and the generated document claims the API needs no
    credentials at all -- the opposite of the truth.
    """

    target_class = "app.core.auth.JWTAuthentication"
    # The name and the definition are the original's, read from its own
    # `/api` document rather than invented: FastAPI declared
    # `OAuth2PasswordBearer(tokenUrl="/api/token")`, which serialises as an
    # oauth2 password flow, not as an http bearer scheme.
    name = "OAuth2PasswordBearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "oauth2",
            "flows": {"password": {"scopes": {}, "tokenUrl": "/api/token"}},
        }


def starlette_route(view):
    """Restrict a documentation route to the methods Starlette gave it.

    FastAPI mounted the schema, Swagger, ReDoc and OAuth2-redirect endpoints
    with `add_route`, which builds a **plain Starlette `Route`** rather than the
    `APIRoute` used for the application's own paths. That one *does* add HEAD
    alongside GET -- so `HEAD /api/docs` is a 200 here, unlike `HEAD /api/v1` --
    but it adds nothing else, and every other method was a 405.

    The Django replacements are `APIView` subclasses, so DRF answered OPTIONS
    with a metadata document instead: 200 and the view's own docstring at
    `/api`, 200 and a page of HTML at `/redoc` and the OAuth2 helper, and at
    `/api/docs` a **500**, because building that document crashed the Swagger
    view's renderer. Verified against the running baseline: all four are
    `405 Method Not Allowed` with `{"detail": "Method Not Allowed"}`.
    """

    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.method.upper() not in ("GET", "HEAD"):
            return JsonResponse({"detail": "Method Not Allowed"}, status=405)
        return view(request, *args, **kwargs)

    return wrapped
