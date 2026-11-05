from django.urls import path

from app.users.views import (
    UserDetailView,
    UserListCreateView,
    UserMeView,
)

urlpatterns = [
    path("users", UserListCreateView.as_view()),
    path("users/me", UserMeView.as_view()),
    # `<str:pk>` on purpose -- see `InvalidUserId` in views.py.
    path("users/<str:user_id>", UserDetailView.as_view()),
]
