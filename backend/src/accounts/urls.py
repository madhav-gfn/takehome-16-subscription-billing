from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = "accounts"

urlpatterns = [
    # POST — email + password → access + refresh tokens
    path("login/", views.CustomTokenObtainPairView.as_view(), name="login"),
    # POST — create new user → access + refresh tokens
    path("register/", views.RegisterView.as_view(), name="register"),
    # POST — refresh token → new access token
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # GET — returns authenticated user's profile
    path("me/", views.MeView.as_view(), name="me"),
    # GET — minimal user directory for owner/collaborator/filter pickers
    path("users/", views.UserListView.as_view(), name="users"),
]
