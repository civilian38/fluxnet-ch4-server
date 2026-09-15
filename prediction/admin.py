from django.contrib import admin
from django import forms
from django.contrib.gis.geos import Point

from leaflet.admin import LeafletGeoAdmin
from .models import Location, WeeklyEnvironmentData, CH4PredictionValue


# ==========================================
# 1. Location Admin Form (위도/경도 수동 입력 지원)
# ==========================================
class LocationAdminForm(forms.ModelForm):
    latitude = forms.FloatField(
        label='위도 (Latitude)',
        required=False,
        help_text='예: 37.5665 (지도를 클릭하거나 숫자를 직접 입력하세요)'
    )
    longitude = forms.FloatField(
        label='경도 (Longitude)',
        required=False,
        help_text='예: 126.9780'
    )

    class Meta:
        model = Location
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 폼 로드 시 point 필드의 필수 입력 해제
        self.fields['point'].required = False

        # 기존 데이터가 있다면 위도/경도 입력칸에 값을 채워넣음
        if self.instance and self.instance.pk and self.instance.point:
            self.fields['latitude'].initial = self.instance.point.y
            self.fields['longitude'].initial = self.instance.point.x

    def clean(self):
        cleaned_data = super().clean()
        lat = cleaned_data.get('latitude')
        lon = cleaned_data.get('longitude')
        point = cleaned_data.get('point')

        initial_point = self.instance.point if self.instance else None
        map_changed = (point != initial_point)

        # 저장 로직 처리
        if map_changed and point is not None:
            # 1. 지도의 마커를 움직였다면 지도의 좌표를 우선 적용
            # 폼의 위도/경도 필드 값도 지도 좌표에 맞춰 업데이트해줍니다.
            cleaned_data['latitude'] = point.y
            cleaned_data['longitude'] = point.x
        elif lat is not None and lon is not None:
            # 2. 지도는 그대로인데 숫자를 입력/수정했다면 숫자로 Point 갱신
            cleaned_data['point'] = Point(lon, lat, srid=4326)

        if not cleaned_data.get('point'):
            self.add_error('point', '지도를 클릭하거나 위도/경도 숫자를 반드시 입력해야 합니다.')

        return cleaned_data


# ==========================================
# 2. Location Admin (LeafletGeoAdmin 적용)
# ==========================================
@admin.register(Location)
class LocationAdmin(LeafletGeoAdmin):
    form = LocationAdminForm

    readonly_fields = ('created_at',)

    # 폼에서 보여질 순서
    fields = ('name', 'latitude', 'longitude', 'point', 'created_at')

    # 목록 화면 설정
    list_display = ('id', 'name', 'display_coordinates', 'created_at')
    search_fields = ('name',)

    def display_coordinates(self, obj):
        # 모델에 정의해두신 get_coordinates() 메서드를 활용할 수도 있습니다.
        # lat, lon = obj.get_coordinates()
        # return f"Lat: {lat}, Lon: {lon}"

        if obj.point:
            return f"Lat: {obj.point.y}, Lon: {obj.point.x}"
        return "-"

    display_coordinates.short_description = '좌표 (위도, 경도)'


# ==========================================
# 3. WeeklyEnvironmentData & CH4PredictionValue Admin
# ==========================================
class CH4PredictionValueInline(admin.StackedInline):
    model = CH4PredictionValue
    extra = 0


@admin.register(WeeklyEnvironmentData)
class WeeklyEnvironmentDataAdmin(admin.ModelAdmin):
    list_display = ('location', 'start_date', 'end_date', 'ta', 'p', 'created_at')
    list_filter = ('location', 'start_date')
    search_fields = ('location__name',)
    date_hierarchy = 'start_date'
    inlines = [CH4PredictionValueInline]

    fieldsets = (
        ('기본 정보', {
            'fields': ('location', 'start_date', 'end_date')
        }),
        ('기상 데이터 (ERA5)', {
            'fields': ('ws', 'ta', 'ts_1', 'ts_2', 'g', 'pa', 'p', 'vpd', 'netrad'),
            'classes': ('collapse',),
        }),
        ('위성 데이터 (Sentinel-1)', {
            'fields': ('vv', 'vh', 'sdwi'),
            'classes': ('collapse',),
        }),
    )


@admin.register(CH4PredictionValue)
class CH4PredictionValueAdmin(admin.ModelAdmin):
    list_display = ('get_location', 'get_start_date', 'value', 'timestamp')
    list_filter = ('timestamp', 'env_data__location')
    search_fields = ('env_data__location__name',)

    def get_location(self, obj):
        return obj.env_data.location.name

    get_location.short_description = '측정 장소'
    get_location.admin_order_field = 'env_data__location'

    def get_start_date(self, obj):
        return obj.env_data.start_date

    get_start_date.short_description = '시작 날짜'
    get_start_date.admin_order_field = 'env_data__start_date'