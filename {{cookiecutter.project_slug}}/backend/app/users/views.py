from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from app.core.auth import IsActiveUser, IsSuperUser, create_user
from app.core.exceptions import RequestValidationError, body_errors
from app.core.parsers import StarletteBodyParser
from app.core.security import get_password_hash
from app.core.views import StarletteDispatchAPIView
from app.users.models import User
from app.users.serializers import (
    UserCreateSerializer,
    UserEditSerializer,
    UserSerializer,
)

#: `get_users(db, skip=0, limit=100)` in the original: the route passed no
#: paging arguments, so a listing was always the first hundred rows.
USER_LIST_LIMIT = 100

#: FastAPI's `user_id: int` rejected a non-integer path segment in the
#: request-validation layer, with 422 and pydantic's error document. Django's
#: `<int:pk>` converter matches `[0-9]+` only, so those requests would never
#: route at all; the route takes the raw segment and validates it here.
INVALID_USER_ID = {
    "loc": ["path", "user_id"],
    "msg": "value is not a valid integer",
    "type": "type_error.integer",
}


def path_errors(user_id):
    """Return `(user_id as int, errors)` for the `{user_id}` path segment."""
    try:
        return int(user_id), []
    except (TypeError, ValueError):
        return None, [INVALID_USER_ID]


def get_user_or_404(user_id):
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise NotFound("User not found")
    return user


def checked_user_id(user_id):
    """Validate a body-less request's path segment."""
    value, errors = path_errors(user_id)
    if errors:
        raise RequestValidationError(errors)
    return value


@extend_schema_view(
    get=extend_schema(operation_id="users_list", tags=["users"]),
    post=extend_schema(operation_id="user_create", tags=["users"]),
)
class UserListCreateView(StarletteDispatchAPIView):
    permission_classes = [IsSuperUser]
    parser_classes = [StarletteBodyParser]

    def get(self, request):
        # `order_by("id")`: the original's query had no ORDER BY and relied on
        # the table's physical order, which PostgreSQL does not keep after an
        # UPDATE. Ordering by the key is what the original returned in practice.
        users = list(User.objects.order_by("id")[:USER_LIST_LIMIT])
        data = UserSerializer(users, many=True).data
        response = Response(data)
        # Content-Range header is consumed by the react-admin frontend.
        response["Content-Range"] = f"0-9/{len(users)}"
        return response

    def post(self, request):
        data, errors = body_errors(UserCreateSerializer, request)
        if errors:
            raise RequestValidationError(errors)
        data = {**UserCreateSerializer.MODEL_DEFAULTS, **data}
        user = create_user(
            email=data["email"],
            password=data["password"],
            is_active=data["is_active"],
            is_superuser=data["is_superuser"],
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
        )
        return Response(UserSerializer(user).data)


@extend_schema_view(
    get=extend_schema(operation_id="user_me", tags=["users"]),
)
class UserMeView(StarletteDispatchAPIView):
    permission_classes = [IsActiveUser]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema_view(
    get=extend_schema(operation_id="user_details", tags=["users"]),
    put=extend_schema(operation_id="user_edit", tags=["users"]),
    delete=extend_schema(operation_id="user_delete", tags=["users"]),
)
class UserDetailView(StarletteDispatchAPIView):
    permission_classes = [IsSuperUser]
    parser_classes = [StarletteBodyParser]

    def get(self, request, user_id):
        user = get_user_or_404(checked_user_id(user_id))
        return Response(UserSerializer(user).data)

    def put(self, request, user_id):
        # FastAPI validated the path and the body together, reporting every
        # error at once, and only then ran the handler -- so an invalid body
        # for a missing user is a 422, not a 404.
        pk, errors = path_errors(user_id)
        data, more = body_errors(UserEditSerializer, request)
        if errors or more:
            raise RequestValidationError(errors + more)
        data = dict(data)
        with transaction.atomic():
            user = get_user_or_404(pk)
            if "password" in data:
                # `None` is a valid `Optional[str]`; hashing it fails, and the
                # transaction keeps the failed edit from writing anything.
                user.hashed_password = get_password_hash(data.pop("password"))
            for field, value in data.items():
                setattr(user, field, value)
            user.save()
        return Response(UserSerializer(user).data)

    def delete(self, request, user_id):
        user = get_user_or_404(checked_user_id(user_id))
        # Serialize before deleting: Django resets the pk after delete().
        data = UserSerializer(user).data
        user.delete()
        return Response(data)
