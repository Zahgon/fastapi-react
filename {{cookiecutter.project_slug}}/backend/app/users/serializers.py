from rest_framework import serializers

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


class UserCreateSerializer(serializers.Serializer):
    # `CharField`, not `EmailField`: the original declared `email: str` on a
    # plain pydantic model and a SQLAlchemy `Column(String)`, so it accepted and
    # stored any string -- `not-an-email` and `a@b.c` both created users.
    # `EmailField` rejects both, which narrows the contract rather than porting
    # it. Migrating is not the place to add validation the original lacked.
    email = serializers.CharField(allow_blank=True)
    password = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField(required=False, default=True)
    is_superuser = serializers.BooleanField(required=False, default=False)
    first_name = serializers.CharField(required=False, allow_null=True)
    last_name = serializers.CharField(required=False, allow_null=True)


class UserEditSerializer(serializers.Serializer):
    # Required, and deliberately so. `UserEdit` subclasses `UserBase`, where
    # `email: str` carries no default, so pydantic demanded it on every PUT --
    # `PUT /users/2` with only a `first_name`, or with an empty body, was a 422
    # naming `email`. Making it optional here turned both into a 200 that
    # silently applied a partial update the original never accepted.
    email = serializers.CharField(allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    is_superuser = serializers.BooleanField(required=False)
    first_name = serializers.CharField(required=False, allow_null=True)
    last_name = serializers.CharField(required=False, allow_null=True)
