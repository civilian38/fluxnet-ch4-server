from rest_framework import viewsets
from rest_framework_gis.filters import InBBoxFilter
from .models import Location
from .serializers import (
    LocationMapSerializer, 
    LocationDetailSerializer, 
    LocationCreateSerializer
)
from .permissions import IsAdminUserOrReadOnly

class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()

    permission_classes = [IsAdminUserOrReadOnly]
    
    bbox_filter_field = 'point'
    filter_backends = (InBBoxFilter, )
    pagination_class = None 

    def get_serializer_class(self):
        if self.action == 'list':
            # GET /api/prediction/locations/
            return LocationMapSerializer
        
        if self.action == 'retrieve':
            # GET /api/prediction/locations/{id}/
            return LocationDetailSerializer
            
        if self.action in ['create', 'update', 'partial_update']:
            # POST, PUT, PATCH 요청
            return LocationCreateSerializer
            
        return super().get_serializer_class()