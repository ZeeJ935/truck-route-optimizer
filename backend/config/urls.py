from django.urls import include, path

urlpatterns = [
    path("api/", include("api.urls")),
]

# The API answers unknown paths and server errors with the standard JSON error envelope.
handler404 = "api.errors.json_not_found"
handler500 = "api.errors.json_server_error"
