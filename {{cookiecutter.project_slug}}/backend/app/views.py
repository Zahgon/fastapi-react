import re
from datetime import timedelta

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.core.auth import authenticate_user, sign_up_new_user
from app.core.celery_app import celery_app
from app.core.exceptions import RequestValidationError
from app.core.parsers import StarletteBodyParser
from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from app.core.views import StarletteDispatchAPIView

#: The credential endpoints read a form and nothing else, but they must not
#: refuse a media type either: `OAuth2PasswordRequestForm` reported the fields
#: it could not find, so a `text/plain` or `application/xml` credential request
#: was a 422 naming `username` and `password`, never a 415. DRF picks a parser
#: by `Content-Type` and raises `UnsupportedMediaType` when none matches, so the
#: two real form parsers are followed by the `*/*` parser already used by the
#: body-taking endpoints. It reads nothing for a non-JSON type, and because the
#: declared type is then not a form type, `request.POST` is an empty QueryDict.
CREDENTIAL_PARSERS = [FormParser, MultiPartParser, StarletteBodyParser]


@extend_schema_view(
    get=extend_schema(operation_id="root"),
)
class RootView(StarletteDispatchAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"message": "Hello World"})


@extend_schema_view(
    get=extend_schema(operation_id="example_task"),
)
class TaskView(StarletteDispatchAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        celery_app.send_task("app.tasks.example_task", args=["Hello World"])
        return Response({"message": "success"})


#: `OAuth2PasswordRequestForm`'s fields, in its signature order, which is the
#: order its validation errors were reported in and the order of its OpenAPI
#: form schema: (name, required, regex, default).
#: `grant_type` was `Form(None, regex="password")`, and pydantic tested the
#: regex with `re.match`, so it must *start* with `password`.
OAUTH2_FORM = (
    ("grant_type", False, "password", None),
    ("username", True, None, None),
    ("password", True, None, None),
    ("scope", False, None, ""),
    ("client_id", False, None, None),
    ("client_secret", False, None, None),
)


def oauth2_form(request):
    """Read the credentials form the way `OAuth2PasswordRequestForm` did.

    `request.POST`, not `request.data`: DRF's `.POST` yields the parsed body
    only for a form media type (urlencoded or multipart) and an empty QueryDict
    otherwise. A JSON body therefore carries no form fields at all, exactly as
    under the original. An empty `grant_type` counts as not sent, which is how
    FastAPI treated empty optional form values. Returns `(fields, errors)`.
    """
    fields, errors = {}, []
    for name, required, pattern, _default in OAUTH2_FORM:
        value = request.POST.get(name)
        if value is None:
            if required:
                errors.append(
                    {
                        "loc": ["body", name],
                        "msg": "field required",
                        "type": "value_error.missing",
                    }
                )
            continue
        if pattern and value and not re.match(pattern, value):
            errors.append(
                {
                    "loc": ["body", name],
                    "msg": f'string does not match regex "{pattern}"',
                    "type": "value_error.str.regex",
                    "ctx": {"pattern": pattern},
                }
            )
            continue
        fields[name] = value
    return fields, errors


def _token_response(user) -> Response:
    permissions = "admin" if user.is_superuser else "user"
    access_token = create_access_token(
        data={"sub": user.email, "permissions": permissions},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Response({"access_token": access_token, "token_type": "bearer"})


@extend_schema_view(
    post=extend_schema(operation_id="login"),
)
class LoginView(StarletteDispatchAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = CREDENTIAL_PARSERS

    def post(self, request):
        form, errors = oauth2_form(request)
        if errors:
            raise RequestValidationError(errors)
        username, password = form["username"], form["password"]
        user = authenticate_user(username, password)
        if not user:
            return Response(
                {"detail": "Incorrect username or password"},
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _token_response(user)


@extend_schema_view(
    post=extend_schema(operation_id="signup"),
)
class SignupView(StarletteDispatchAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = CREDENTIAL_PARSERS

    def post(self, request):
        form, errors = oauth2_form(request)
        if errors:
            raise RequestValidationError(errors)
        username, password = form["username"], form["password"]
        user = sign_up_new_user(username, password)
        if not user:
            return Response(
                {"detail": "Account already exists"},
                status=409,
                # The original raised HTTPException(409, ...,
                # headers={"WWW-Authenticate": "Bearer"}). Odd on a conflict,
                # but it is what the endpoint sent.
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _token_response(user)
