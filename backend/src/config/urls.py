from django.http import JsonResponse
from django.urls import include, path


def health(request):
    return JsonResponse({
        "service": "django",
        "message": "Hello from the Django backend",
        "status": "ok",
    })


urlpatterns = [
    path("health/", health, name="health"),
    path("api/auth/", include("src.accounts.urls")),
    path("", health, name="home"),
]
