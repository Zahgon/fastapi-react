import jwt
from rest_framework import exceptions, permissions
from rest_framework.authentication import (
    BaseAuthentication,
    get_authorization_header,
)

from app.core import security
from app.core.security import get_password_hash
from app.users.models import User


def get_user_by_email(email):
    return User.objects.filter(email=email).first()


def create_user(
    email,
    password,
    is_active=True,
    is_superuser=False,
    first_name=None,
    last_name=None,
):
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_active=is_active,
        is_superuser=is_superuser,
        hashed_password=get_password_hash(password),
    )
    user.save()
    return user


def authenticate_user(email, password):
    user = get_user_by_email(email)
    if not user:
        return False
    if not security.verify_password(password, user.hashed_password):
        return False
    return user


def sign_up_new_user(email, password):
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
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != b"bearer":
            return None
        if len(auth) != 2:
            raise exceptions.AuthenticationFailed(
                "Could not validate credentials"
            )
        token = auth[1].decode("utf-8")
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


class IsSuperUser(permissions.BasePermission):
    """Allow only authenticated, active superusers."""

    def has_permission(self, request, view):
        if request.successful_authenticator is None:
            return False
        if not request.user.is_active:
            raise InactiveUser()
        if not request.user.is_superuser:
            return False
        return True
