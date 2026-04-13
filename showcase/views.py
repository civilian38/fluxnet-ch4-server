from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from .serializers import LocationSerializer, DataSerializer
from .models import Location, CH4Data
from .permissions import IsAdminOrReadOnly

# Location
class LocationListCreateView(ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly, ]
    pagination_class = None
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

# Data (List & Create)
class DataListCreateView(ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly, ]
    serializer_class = DataSerializer

    def get_queryset(self):
        location_id = self.kwargs.get('location_id')
        location = Location.objects.get(id=location_id)
        return CH4Data.objects.filter(location=location)

# Data (Retrieve & Update & Destroy)
class DataRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly, ]
    serializer_class = DataSerializer
    queryset = CH4Data.objects.all()

# Data to show if first click
class LatestDataRetrieveView(RetrieveAPIView):
    permission_classes = [AllowAny, ]
    serializer_class = DataSerializer

    def get_object(self):
        location_id = self.kwargs.get('location_id')
        obj = CH4Data.objects.filter(location=location_id).first()
        return obj