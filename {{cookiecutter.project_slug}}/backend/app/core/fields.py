"""Serializer fields that coerce input the way pydantic 1 did.

DRF's `CharField` trims surrounding whitespace and refuses booleans; its
`BooleanField` has its own table of spellings. The original validated its
request bodies with pydantic, whose `str` and `bool` rules differ from both, and
those rules decide which requests succeed and what gets stored. These fields
reproduce them so the port accepts, coerces and rejects exactly the same values.
"""

from rest_framework import serializers

#: pydantic's `BOOL_TRUE` / `BOOL_FALSE`, compared after lower-casing strings.
_TRUE = {1, "1", "on", "t", "true", "y", "yes"}
_FALSE = {0, "0", "off", "f", "false", "n", "no"}


class PydanticStrField(serializers.Field):
    """pydantic's `str`: strings as given, numbers stringified, nothing else."""

    default_error_messages = {"str": "str type expected"}

    def to_internal_value(self, data):
        if isinstance(data, str):
            return data
        # `bool` is an `int`, so `True` becomes "True", as pydantic made it.
        if isinstance(data, (int, float)):
            return str(data)
        self.fail("str")

    def to_representation(self, value):
        return value


class PydanticBoolField(serializers.Field):
    """pydantic's `bool`: its own spellings, case-insensitive for strings."""

    default_error_messages = {"bool": "value could not be parsed to a boolean"}

    def to_internal_value(self, data):
        if data is True or data is False:
            return data
        if isinstance(data, str):
            data = data.lower()
        try:
            if data in _TRUE:
                return True
            if data in _FALSE:
                return False
        except TypeError:
            # Unhashable input (a list or an object) is simply not a boolean.
            self.fail("bool")
        self.fail("bool")

    def to_representation(self, value):
        return value
