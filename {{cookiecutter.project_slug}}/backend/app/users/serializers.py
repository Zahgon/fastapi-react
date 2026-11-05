from rest_framework import serializers

from app.core.fields import PydanticBoolField, PydanticStrField
from app.users.models import User


class UserSerializer(serializers.ModelSerializer):
    """Output serializer that drops keys whose value is ``None`` (e.g. an unset
    first/last name), so absent optional fields are omitted from responses."""

    class Meta:
        model = User
        # Field order is part of the wire contract: pydantic emitted the
        # `UserBase` fields first and `id` last, because `User(UserBase)` is
        # what adds it. DRF serialises in declaration order, so the list has to
        # match or every payload comes back with its keys in a different order.
        fields = [
            "email",
            "is_active",
            "is_superuser",
            "first_name",
            "last_name",
            "id",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {key: value for key, value in data.items() if value is not None}


class UserBaseSerializer(serializers.Serializer):
    """The fields of the original `UserBase` model, in its declaration order.

    pydantic reported validation errors in field order, so the order here is
    the order of the `detail` list a client receives. `email` accepts any
    string -- the original declared `email: str`, not an email type.

    The two booleans carry pydantic's defaults in `MODEL_DEFAULTS` rather than
    as DRF defaults: a create applies them, but an edit, like the original's
    `user.dict(exclude_unset=True)`, changes only the fields it was sent.
    """

    MODEL_DEFAULTS = {"is_active": True, "is_superuser": False}

    email = PydanticStrField()
    is_active = PydanticBoolField(required=False)
    is_superuser = PydanticBoolField(required=False)
    first_name = PydanticStrField(required=False, allow_null=True)
    last_name = PydanticStrField(required=False, allow_null=True)


class UserCreateSerializer(UserBaseSerializer):
    password = PydanticStrField()


class UserEditSerializer(UserBaseSerializer):
    # `Optional[str] = None` in the original: an explicit null is accepted, and
    # hashing it then fails the request -- see `UserDetailView.put`.
    password = PydanticStrField(required=False, allow_null=True)
