from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("routes/analyze", views.analyze_routes, name="analyze-routes"),
    path("places/suggest", views.suggest_places, name="suggest-places"),
]
