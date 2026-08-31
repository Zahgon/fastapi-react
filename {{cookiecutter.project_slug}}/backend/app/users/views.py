from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response
from app.core.views import StarletteDispatchAPIView

from app.core.auth import IsActiveUser, IsSuperUser, create_user
from app.core.exceptions import validated
from app.core.parsers import StarletteBodyParser
from app.core.security import get_password_hash
from app.users.models import User
from app.users.serializers import (
    UserCreateSerializer,
    UserEditSerializer,
    UserSerializer,
)


class InvalidUserId(APIException):
    """FastAPI's `user_id: int` rejected a non-integer path segment in the
    request-validation layer, with 422 and pydantic's error document. Django's
    `<int:pk>` converter matches `[0-9]+` only, so those requests never routed
    at all and the resolver answered an HTML 404 before any application code
    ran. The route now takes the raw segment and this runs instead."""

    status_code = 422

    def __init__(self):
        super().__init__(
            {
                "detail": [
                    {
                        "loc": ["path", "user_id"],
                        "msg": "value is not a valid integer",
                        "type": "type_error.integer",
                    }
                ]
            }
        )


def parse_user_id(pk):
    try:
        return int(pk)
    except (TypeError, ValueError):
        raise InvalidUserId()


def get_user_or_404(pk):
    user = User.objects.filter(pk=parse_user_id(pk)).first()
    if user is None:
        raise NotFound("User not found")
    return user


@extend_schema_view(
    get=extend_schema(
        operation_id="users_list", responses={200: UserSerializer(many=True)}
    ),
    post=extend_schema(
        operation_id="user_create",
        request=UserCreateSerializer,
        responses={200: UserSerializer, 422: None},
    ),
)
class UserListCreateView(StarletteDispatchAPIView):
    permission_classes = [IsSuperUser]
    parser_classes = [StarletteBodyParser]

    def get(self, request):
        users = list(User.objects.all())
        data = UserSerializer(users, many=True).data
        response = Response(data)
        # Content-Range header is consumed by the react-admin frontend.
        response["Content-Range"] = f"0-9/{len(users)}"
        return response

    def post(self, request):
        data = validated(UserCreateSerializer(data=request.data), request)
        user = create_user(
            email=data["email"],
            password=data["password"],
            is_active=data.get("is_active", True),
            is_superuser=data.get("is_superuser", False),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
        )
        return Response(UserSerializer(user).data)


@extend_schema_view(
    get=extend_schema(
        operation_id="user_me", responses={200: UserSerializer, 401: None}
    ),
)
class UserMeView(StarletteDispatchAPIView):
    permission_classes = [IsActiveUser]

    def dispatch(self, request, *args, **kwargs):
        """Hand every method but `GET` to the `/users/{user_id}` route.

        Starlette scanned its route table for a *method* match, not merely a
        path match: `/users/me` was declared `GET`-only, so `PUT
        /api/v1/users/me` did not stop there. It carried on to
        `/users/{user_id}` -- whose path parameter is an unconstrained segment,
        so `me` matched -- and was answered by that route, which is why the
        original returned **401** from the superuser dependency rather than a
        405. Django's resolver stops at the first pattern whose path matches
        and never reconsiders, so the fall-through is reproduced here.
        """
        if request.method.upper() != "GET":
            return _user_detail(request, user_id="me")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema_view(
    get=extend_schema(
        operation_id="user_details", responses={200: UserSerializer, 404: None}
    ),
    put=extend_schema(
        operation_id="user_edit",
        request=UserEditSerializer,
        responses={200: UserSerializer, 404: None, 422: None},
    ),
    delete=extend_schema(
        operation_id="user_delete", responses={200: UserSerializer, 404: None}
    ),
)
class UserDetailView(StarletteDispatchAPIView):
    permission_classes = [IsSuperUser]
    parser_classes = [StarletteBodyParser]

    def get(self, request, user_id):
        user = get_user_or_404(user_id)
        return Response(UserSerializer(user).data)

    def put(self, request, user_id):
        user = get_user_or_404(user_id)
        data = dict(validated(UserEditSerializer(data=request.data), request))
        if "password" in data:
            user.hashed_password = get_password_hash(data.pop("password"))
        for field, value in data.items():
            setattr(user, field, value)
        user.save()
        return Response(UserSerializer(user).data)

    def delete(self, request, user_id):
        user = get_user_or_404(user_id)
        # Serialize before deleting: Django resets the pk after delete().
        data = UserSerializer(user).data
        user.delete()
        return Response(data)


#: Built once; `UserMeView.dispatch` delegates to it.
_user_detail = UserDetailView.as_view()
