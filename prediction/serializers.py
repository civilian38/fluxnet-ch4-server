from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from django.contrib.gis.geos import Point # Point 객체 생성용
from .models import Location, WeeklyEnvironmentData

# 1. 지도 마커 렌더링용 (가벼운 GeoJSON)
class LocationMapSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Location
        geo_field = "point"
        fields = ['id', 'name'] 

# 2. 마커 클릭 시 상세 정보용 (상세한 일반 JSON)
class LocationDetailSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(source='point.y', read_only=True)
    longitude = serializers.FloatField(source='point.x', read_only=True)
    latest_ch4_prediction = serializers.SerializerMethodField()

    class Meta:
        model = Location
        fields = ['id', 'name', 'latitude', 'longitude', 'created_at', 'latest_ch4_prediction']

    def get_latest_ch4_prediction(self, obj):
        latest_env_data = obj.weekly_data.filter(prediction_value__isnull=False).first()
        
        # 데이터가 존재한다면 해당 CH4 값을 반환, 없다면 None 반환
        if latest_env_data:
            return latest_env_data.prediction_value.value
        
        return None

# 3. 장소 생성용 Serializer
class LocationCreateSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(write_only=True)
    longitude = serializers.FloatField(write_only=True)

    class Meta:
        model = Location
        fields = ['id', 'name', 'latitude', 'longitude'] 

    def create(self, validated_data):
        latitude = validated_data.pop('latitude')
        longitude = validated_data.pop('longitude')

        point = Point(longitude, latitude, srid=4326)
        
        validated_data['point'] = point

        return super().create(validated_data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.point:
            ret['latitude'] = instance.point.y
            ret['longitude'] = instance.point.x
        return ret

class CH4TrendSerializer(serializers.ModelSerializer):
    # OneToOne 필드인 prediction_value에서 value 값만 추출
    ch4_value = serializers.FloatField(source='prediction_value.value', read_only=True)
    date = serializers.DateField(source='start_date')

    class Meta:
        model = WeeklyEnvironmentData
        fields = ['date', 'ch4_value']