from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions



urlpatterns = [
    path("admin/", admin.site.urls),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),

    # api
    path('api/authentication/', include('authentication.urls')),
]