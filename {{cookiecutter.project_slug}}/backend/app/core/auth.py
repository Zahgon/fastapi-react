import jwt
from django.db import transaction
from rest_framework import exceptions, permissions
from rest_framework.authentication import (
    BaseAuthentication,
    get_authorization_header,
)

from app.core import security
from app.core.security import get_password_hash
from app.users.models import User


def get_user_by_email(email: str) -> User:
    return User.objects.filter(email=email).first()


def create_user(
    email: str,
    password: str,
    is_active: bool = True,
    is_superuser: bool = False,
    first_name: str = None,
    last_name: str = None,
) -> User:
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_active=is_active,
        is_superuser=is_superuser,
        hashed_password=get_password_hash(password),
    )
    # A savepoint, so a unique-email violation rolls back this write alone and
    # leaves any enclosing transaction usable -- SQLAlchemy's session did the
    # same when the original's commit failed.
    with transaction.atomic():
        user.save()
    return user


def authenticate_user(email: str, password: str):
    user = get_user_by_email(email)
    if not user:
        return False
    if not security.verify_password(password, user.hashed_password):
        return False
    return user


def sign_up_new_user(email: str, password: str):
    user = get_user_by_email(email)
    if user:
        # User with that email already exists.
        return False
    return create_user(email, password, is_active=True, is_superuser=False)


class InactiveUser(exceptions.APIException):
    status_code = 400
    default_detail = "Inactive user"
    default_code = "inactive_user"


class JWTAuthentication(BaseAuthentication):
    """DRF authenticator that validates the JWTs issued by the login/signup
    endpoints: decode the token and load the user named by the ``sub`` claim."""

    def authenticate(self, request):
        # Split the header the way FastAPI's `get_authorization_scheme_param`
        # did: at the first space only. A second space stays in the token and
        # makes it undecodable, as it did there.
        header = get_authorization_header(request).decode("latin-1")
        scheme, _, token = header.partition(" ")
        if not header or scheme.lower() != "bearer":
            return None
        try:
            payload = jwt.decode(
                token, security.SECRET_KEY, algorithms=[security.ALGORITHM]
            )
            email = payload.get("sub")
        except jwt.PyJWTError:
            raise exceptions.AuthenticationFailed(
                "Could not validate credentials"
            )
        if email is None:
            raise exceptions.AuthenticationFailed(
                "Could not validate credentials"
            )
        user = get_user_by_email(email)
        if user is None:
            raise exceptions.AuthenticationFailed(
                "Could not validate credentials"
            )
        return (user, token)

    def authenticate_header(self, request):
        # Returning a value makes DRF answer with 401 (not 403) when
        # authentication is required but missing/invalid.
        return "Bearer"


class IsActiveUser(permissions.BasePermission):
    """Allow only authenticated, active users."""

    def has_permission(self, request, view):
        if request.successful_authenticator is None:
            return False
        if not request.user.is_active:
            raise InactiveUser()
        return True


class IsSuperUser(IsActiveUser):
    """Allow only authenticated, active superusers."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_superuser
