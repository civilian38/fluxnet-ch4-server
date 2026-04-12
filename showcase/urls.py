from django.urls import path
from .views import LocationListCreateView, DataListCreateView, DataRetrieveUpdateDestroyView, LatestDataRetrieveView

urlpatterns = [
    path('locations/', LocationListCreateView.as_view(), name='location-list-create'),
    path('location/<int:location_id>/data/', DataListCreateView.as_view(), name='data-list-create'),
    path('data/<int:pk>/', DataRetrieveUpdateDestroyView.as_view(), name='data-retrieve-update-destroy'),
    path('location/<int:location_id>/data/latest/', LatestDataRetrieveView.as_view(), name='latest-data')
]