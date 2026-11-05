"""The OpenAPI document FastAPI generated, rebuilt from the Django routes.

`drf-spectacular` walks the URLconf and the authentication classes, which gives
the paths, the methods and each operation's security requirement. Everything
else in FastAPI's document came from its own conventions -- operation ids made
from the endpoint name and path, summaries from the endpoint name, pydantic
model schemas, form bodies named `Body_<operationId>`, and a 422 response
wherever a request could fail validation. A plain `APIView` declares none of
that, so this post-processing hook rewrites each operation in FastAPI's form
from the views' operation names and the serializers' fields.
"""

import re

from django.conf import settings

from app.core.fields import PydanticBoolField, PydanticStrField

#: Per endpoint (the view's `operation_id`): its router tags, its request
#: body as (component kind, media type), and the model it answers with.
OPERATIONS = {
    "root": {"tags": None, "body": None, "response": None},
    "example_task": {"tags": None, "body": None, "response": None},
    "users_list": {"tags": ["users"], "body": None, "response": "list"},
    "user_create": {
        "tags": ["users"],
        "body": ("UserCreate", "application/json"),
        "response": "User",
    },
    "user_me": {"tags": ["users"], "body": None, "response": "User"},
    "user_details": {"tags": ["users"], "body": None, "response": "User"},
    "user_edit": {
        "tags": ["users"],
        "body": ("UserEdit", "application/json"),
        "response": "User",
    },
    "user_delete": {"tags": ["users"], "body": None, "response": "User"},
    "login": {
        "tags": ["auth"],
        "body": ("form", "application/x-www-form-urlencoded"),
        "response": None,
    },
    "signup": {
        "tags": ["auth"],
        "body": ("form", "application/x-www-form-urlencoded"),
        "response": None,
    },
}

#: Every path parameter in this API is an integer id.
PATH_PARAMETER_TYPES = {"user_id": "integer"}

VALIDATION_COMPONENTS = {
    "HTTPValidationError": {
        "title": "HTTPValidationError",
        "type": "object",
        "properties": {
            "detail": {
                "title": "Detail",
                "type": "array",
                "items": {"$ref": "#/components/schemas/ValidationError"},
            }
        },
    },
    "ValidationError": {
        "title": "ValidationError",
        "required": ["loc", "msg", "type"],
        "type": "object",
        "properties": {
            "loc": {"title": "Location", "type": "array", "items": {"type": "string"}},
            "msg": {"title": "Message", "type": "string"},
            "type": {"title": "Error Type", "type": "string"},
        },
    },
}


def _title(name):
    return name.replace("_", " ").title()


def _ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def _model_schema(name, fields, defaults, extra=()):
    """pydantic 1's `Model.schema()` for a serializer's fields."""
    properties, required = {}, []
    for field_name, field in fields.items():
        prop = {"title": _title(field_name)}
        if isinstance(field, PydanticBoolField):
            prop["type"] = "boolean"
        elif isinstance(field, PydanticStrField):
            prop["type"] = "string"
        else:
            raise TypeError(f"no schema mapping for {type(field).__name__}")
        if field_name in defaults:
            prop["default"] = defaults[field_name]
        properties[field_name] = prop
        if field.required:
            required.append(field_name)
    for field_name, type_ in extra:
        properties[field_name] = {"title": _title(field_name), "type": type_}
        required.append(field_name)
    schema = {"title": name}
    if required:
        schema["required"] = required
    schema.update(type="object", properties=properties)
    return schema


def _form_schema(name):
    from app.views import OAUTH2_FORM

    properties, required = {}, []
    for field_name, is_required, pattern, default in OAUTH2_FORM:
        prop = {"title": _title(field_name), "type": "string"}
        if pattern:
            prop["pattern"] = pattern
        if default is not None:
            prop["default"] = default
        properties[field_name] = prop
        if is_required:
            required.append(field_name)
    return {
        "title": name,
        "required": required,
        "type": "object",
        "properties": properties,
    }


def _component_schemas(form_bodies):
    from app.users.serializers import (
        UserBaseSerializer,
        UserCreateSerializer,
        UserEditSerializer,
    )

    defaults = UserBaseSerializer.MODEL_DEFAULTS
    schemas = {
        "User": _model_schema(
            "User", UserBaseSerializer().fields, defaults, [("id", "integer")]
        ),
        "UserCreate": _model_schema(
            "UserCreate", UserCreateSerializer().fields, defaults
        ),
        "UserEdit": _model_schema("UserEdit", UserEditSerializer().fields, defaults),
        **VALIDATION_COMPONENTS,
    }
    for name in form_bodies:
        schemas[name] = _form_schema(name)
    return dict(sorted(schemas.items()))


def _operation(name, path, method, generated, form_bodies):
    spec = OPERATIONS[name]
    operation_id = re.sub(r"[^0-9a-zA-Z_]", "_", name + path) + "_" + method
    operation = {}
    if spec["tags"]:
        operation["tags"] = spec["tags"]
    operation["summary"] = _title(name)
    operation["operationId"] = operation_id
    parameters = [
        {
            "required": True,
            "schema": {"title": _title(param), "type": PATH_PARAMETER_TYPES[param]},
            "name": param,
            "in": "path",
        }
        for param in re.findall(r"{(\w+)}", path)
    ]
    if parameters:
        operation["parameters"] = parameters
    if spec["body"]:
        kind, media_type = spec["body"]
        if kind == "form":
            kind = f"Body_{operation_id}"
            form_bodies.append(kind)
        operation["requestBody"] = {
            "content": {media_type: {"schema": _ref(kind)}},
            "required": True,
        }
    if spec["response"] == "list":
        body = {
            "title": _title(f"response_{operation_id}"),
            "type": "array",
            "items": _ref("User"),
        }
    elif spec["response"]:
        body = _ref(spec["response"])
    else:
        body = {}
    operation["responses"] = {
        "200": {
            "description": "Successful Response",
            "content": {"application/json": {"schema": body}},
        }
    }
    if parameters or spec["body"]:
        operation["responses"]["422"] = {
            "description": "Validation Error",
            "content": {"application/json": {"schema": _ref("HTTPValidationError")}},
        }
    # `drf-spectacular` lists `{}` (no credentials) for views without an
    # authenticator; FastAPI listed only the schemes a route required.
    security = [
        requirement for requirement in generated.get("security", []) if requirement
    ]
    if security:
        operation["security"] = security
    return operation


def fastapi_document(result, generator, request, public):
    """`drf-spectacular` post-processing hook: FastAPI's document shape."""
    form_bodies = []
    paths = {
        path: {
            method: _operation(
                generated["operationId"], path, method, generated, form_bodies
            )
            for method, generated in methods.items()
        }
        for path, methods in result["paths"].items()
    }
    components = {"schemas": _component_schemas(form_bodies)}
    security_schemes = result.get("components", {}).get("securitySchemes")
    if security_schemes:
        components["securitySchemes"] = security_schemes
    return {
        "openapi": "3.0.2",
        "info": {
            "title": settings.PROJECT_NAME,
            "version": settings.SPECTACULAR_SETTINGS["VERSION"],
        },
        "paths": paths,
        "components": components,
    }
