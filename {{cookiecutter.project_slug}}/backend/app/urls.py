from django.urls import include, path
from drf_spectacular.views import SpectacularRedocView, SpectacularSwaggerView

from app.core.handlers import not_found, server_error
from app.core.schema import SchemaView, oauth2_redirect, starlette_route
from app.views import LoginView, RootView, SignupView, TaskView

urlpatterns = [
    path("api/v1", RootView.as_view()),
    path("api/v1/task", TaskView.as_view()),
    path("api/token", LoginView.as_view()),
    path("api/signup", SignupView.as_view()),
    path("api/v1/", include("app.users.urls")),
    # FastAPI generated these four automatically: the schema at `openapi_url`
    # ("/api"), Swagger at `docs_url` ("/api/docs"), and ReDoc plus the OAuth2
    # redirect helper at Starlette's defaults. Django generates none of them,
    # and the port had dropped all four.
    # `starlette_route` keeps these four to GET and HEAD, the way a plain
    # Starlette `Route` did -- see `app/core/schema.py`.
    path("api", starlette_route(SchemaView.as_view()), name="schema"),
    path(
        "api/docs",
        starlette_route(SpectacularSwaggerView.as_view(url_name="schema")),
    ),
    path(
        "redoc",
        starlette_route(SpectacularRedocView.as_view(url_name="schema")),
    ),
    path("docs/oauth2-redirect", starlette_route(oauth2_redirect)),
]

handler404 = not_found
handler500 = server_error
