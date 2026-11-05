import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

# Project metadata.
PROJECT_NAME = "{{cookiecutter.project_name}}"
API_V1_STR = "/api/v1"

# Secret key used both by Django and for signing JWTs (see app/core/security.py).
SECRET_KEY = "{{cookiecutter.secret_key}}"

# The original had no debug mode at all. Hardcoding `True` shipped every
# rendered project with Django's traceback page -- full settings and local
# variables on any error -- which is behaviour the migration introduced
# rather than ported. Off unless asked for.
DEBUG = os.environ.get("DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    # Generates the OpenAPI document and the two documentation UIs that FastAPI
    # provided automatically at /api, /api/docs, /redoc and
    # /docs/oauth2-redirect. Django provides none of them.
    "drf_spectacular",
    "app.users",
]

MIDDLEWARE = [
    "app.core.middleware.StarletteResponseHeaders",
    "app.core.middleware.StarletteSlashRedirect",
    # Innermost on purpose: it answers a method miss by re-dispatching, and the
    # response it substitutes still has to leave through the header pipeline.
    "app.core.middleware.StarletteMethodResolution",
]

# No `CommonMiddleware`. Its only jobs here would be `APPEND_SLASH` -- a 301
# for a subset of what Starlette answered with a 307 in both directions, which
# `StarletteSlashRedirect` does instead -- and validating the `Host` header via
# `request.get_host()`. Starlette served any `Host`, and Docker Compose service
# names such as `backend_1` contain underscores that Django's host check
# rejects with a 400. `StarletteResponseHeaders` sets `content-length` itself.
APPEND_SLASH = False

ROOT_URLCONF = "app.urls"
WSGI_APPLICATION = "app.wsgi.application"
ASGI_APPLICATION = "app.asgi.application"

# Database: honour DATABASE_URL (Postgres, as used by docker-compose) when set,
# otherwise fall back to a local SQLite database.
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Read the URL the way SQLAlchemy's `make_url` did for the original
    # `create_engine(DATABASE_URL)`: percent-encoded credentials are decoded,
    # and query parameters (`sslmode=require`, ...) go to the driver.
    _url = urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _url.path.lstrip("/"),
            "USER": unquote(_url.username or ""),
            "PASSWORD": unquote(_url.password or ""),
            "HOST": _url.hostname or "",
            "PORT": _url.port or "",
            "OPTIONS": dict(parse_qsl(_url.query)),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# `drf_spectacular` renders the Swagger and ReDoc pages from packaged
# templates, and its static assets are served from the package too. The
# original application needed neither -- FastAPI shipped both UIs itself -- so
# this settings module had no template or static configuration at all.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "app.core.auth.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # Reproduce FastAPI's HTTP 422 for request-validation failures.
    "EXCEPTION_HANDLER": "app.core.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # FastAPI never read `Accept` or a `?format=` parameter: every response
    # had exactly one representation, so neither may select or reject one.
    "DEFAULT_CONTENT_NEGOTIATION_CLASS": "app.core.negotiation.JSONOnlyNegotiation",
    "URL_FORMAT_OVERRIDE": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "{{cookiecutter.project_name}}",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # FastAPI's Swagger page sent the OAuth2 flow back to the redirect helper it
    # served at /docs/oauth2-redirect; a string is inserted as a JS expression.
    "SWAGGER_UI_SETTINGS": """{
        "deepLinking": true,
        "oauth2RedirectUrl": window.location.origin + "/docs/oauth2-redirect"
    }""",
    # Rewrites the generated document into the shape FastAPI produced.
    "POSTPROCESSING_HOOKS": ["app.core.openapi.fastapi_document"],
}

# The "user" table uses a plain integer primary key.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

USE_TZ = True
