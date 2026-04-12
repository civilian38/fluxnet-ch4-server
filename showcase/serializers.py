from rest_framework import serializers

from .models import Location, CH4Data

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'

class DataSerializer(serializers.ModelSerializer):
    location = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CH4Data
        fields = '__all__'
