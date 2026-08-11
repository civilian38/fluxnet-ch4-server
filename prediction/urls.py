from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LocationViewSet

app_name = 'prediction'

router = DefaultRouter()
router.register(r'locations', LocationViewSet, basename='location')

urlpatterns = [
    path('', include(router.urls)),
]