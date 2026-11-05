import os

import django


def init() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
    django.setup()

    from app.core.auth import create_user, get_user_by_email

    email = "{{cookiecutter.superuser_email}}"
    if get_user_by_email(email):
        print(f"Superuser {email} already exists")
        return

    print(f"Creating superuser {email}")
    create_user(
        email=email,
        password="{{cookiecutter.superuser_password}}",
        is_active=True,
        is_superuser=True,
    )
    print("Superuser created")


if __name__ == "__main__":
    init()
