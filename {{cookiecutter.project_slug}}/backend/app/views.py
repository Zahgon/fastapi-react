from datetime import timedelta

from drf_spectacular.utils import extend_schema, extend_schema_view

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from app.core.views import StarletteDispatchAPIView

from app.core.auth import authenticate_user, sign_up_new_user
from app.core.celery_app import celery_app
from app.core.openapi import CREDENTIALS, MESSAGE, TOKEN
from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token


@extend_schema_view(
    get=extend_schema(operation_id="root", responses={200: MESSAGE}),
)
class RootView(StarletteDispatchAPIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"message": "Hello World"})


@extend_schema_view(
    get=extend_schema(operation_id="example_task", responses={200: MESSAGE}),
)
class TaskView(StarletteDispatchAPIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        celery_app.send_task("app.tasks.example_task", args=["Hello World"])
        return Response({"message": "success"})


def _missing_credentials(request):
    """Reject bodies that omit a credential field.

    FastAPI declared both endpoints with ``OAuth2PasswordRequestForm``, so an
    absent ``username`` or ``password`` never reached the handler -- it was
    answered with a 422 by the framework. Reproduce that response instead of
    letting ``None`` flow into the database layer. An empty string is a
    present value and passes here, exactly as it did under the form model.
    """
    # `request.POST`, not `request.data`: DRF's `.POST` yields the parsed body
    # only when the content type is a form media type, and an empty QueryDict
    # otherwise. That is what `OAuth2PasswordRequestForm` did -- a JSON body
    # carried no form fields, so both credentials were missing and the request
    # was a 422. Reading `request.data` accepts JSON and quietly widens the
    # endpoint: a JSON signup would create an account the original refused.
    errors = [
        {
            "loc": ["body", field],
            "msg": "field required",
            "type": "value_error.missing",
        }
        for field in ("username", "password")
        if request.POST.get(field) is None
    ]
    if not errors:
        return None
    return Response({"detail": errors}, status=422)


def _token_response(user) -> Response:
    permissions = "admin" if user.is_superuser else "user"
    access_token = create_access_token(
        data={"sub": user.email, "permissions": permissions},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Response({"access_token": access_token, "token_type": "bearer"})


@extend_schema_view(
    post=extend_schema(
        operation_id="login",
        request=CREDENTIALS,
        responses={200: TOKEN, 401: None, 422: None},
    ),
)
class LoginView(StarletteDispatchAPIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        invalid = _missing_credentials(request)
        if invalid is not None:
            return invalid
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate_user(username, password)
        if not user:
            return Response(
                {"detail": "Incorrect username or password"},
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _token_response(user)


@extend_schema_view(
    post=extend_schema(
        operation_id="signup",
        request=CREDENTIALS,
        responses={200: TOKEN, 409: None, 422: None},
    ),
)
class SignupView(StarletteDispatchAPIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        invalid = _missing_credentials(request)
        if invalid is not None:
            return invalid
        username = request.POST.get("username")
        password = request.POST.get("password")
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
