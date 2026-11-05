from django.db import models


class UnboundedCharField(models.TextField):
    """A `varchar` with no length limit.

    SQLAlchemy's `Column(String)` with no length emits an unbounded
    `VARCHAR`, and the original accepted strings of any size. Django's
    `CharField` requires a `max_length`, and `TextField` would emit `text` --
    a different column type. This keeps the type and drops the limit.
    """

    def db_type(self, connection):
        return "varchar"


class User(models.Model):
    """Plain Django model backing the ``user`` table. Authentication is handled
    by a custom JWT scheme, so this intentionally does not extend
    django.contrib.auth's AbstractBaseUser.

    Column types and nullability follow the SQLAlchemy original exactly: every
    string column is an unbounded `varchar`, and the two booleans are nullable
    because `Column(Boolean, default=True)` never said otherwise.
    """

    # `unique=True` would emit a UNIQUE CONSTRAINT plus a `_like` index; the
    # original had a single unique btree named `ix_user_email`. The constraint
    # below reproduces it by name.
    email = UnboundedCharField()
    first_name = UnboundedCharField(null=True, blank=True)
    last_name = UnboundedCharField(null=True, blank=True)
    hashed_password = UnboundedCharField()
    is_active = models.BooleanField(default=True, null=True)
    is_superuser = models.BooleanField(default=False, null=True)

    class Meta:
        db_table = "user"
        indexes = [models.Index(fields=["id"], name="ix_user_id")]
        constraints = [
            models.UniqueConstraint(fields=["email"], name="ix_user_email")
        ]

    def __str__(self):
        return self.email
