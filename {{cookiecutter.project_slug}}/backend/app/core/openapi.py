"""Response shapes the schema generator cannot infer from a plain `APIView`.

`drf-spectacular` reads serializers off `GenericAPIView`; these views are plain
`APIView`s, so every operation has to say what it returns. Without this the
generated document carries no response bodies at all, which is thinner than the
one FastAPI derived from its `response_model=` declarations.
"""

from drf_spectacular.utils import inline_serializer
from rest_framework import serializers

MESSAGE = inline_serializer("Message", {"message": serializers.CharField()})
TOKEN = inline_serializer(
    "Token",
    {
        "access_token": serializers.CharField(),
        "token_type": serializers.CharField(),
    },
)
CREDENTIALS = inline_serializer(
    "Credentials",
    {
        "username": serializers.CharField(),
        "password": serializers.CharField(),
    },
)
