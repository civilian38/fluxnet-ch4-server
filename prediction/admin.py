from django import forms
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.contrib.gis.geos import Point
from .models import Location, WeeklyEnvironmentData


# 1. Location 전용 커스텀 Form 생성
class LocationAdminForm(forms.ModelForm):
    # 숫자를 직접 입력할 수 있는 커스텀 필드 추가
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
        # 지도를 클릭하지 않고 숫자만 입력할 수도 있으므로 point 필드의 필수 입력 해제
        self.fields['point'].required = False

        # 이미 저장된 데이터가 있다면 위도/경도 텍스트 입력칸에 값을 채워넣음
        if self.instance and self.instance.pk and self.instance.point:
            self.fields['latitude'].initial = self.instance.point.y
            self.fields['longitude'].initial = self.instance.point.x

    def clean(self):
        cleaned_data = super().clean()
        lat = cleaned_data.get('latitude')
        lon = cleaned_data.get('longitude')
        point = cleaned_data.get('point')

        # 폼 로드 시점의 기존 좌표
        initial_point = self.instance.point if self.instance else None

        # 지도 마커가 변경되었는지 확인
        map_changed = (point != initial_point)

        # 저장 로직 (지도 vs 숫자 입력)
        if map_changed and point is not None:
            # 1. 지도의 마커를 움직였다면 지도의 좌표를 우선 적용 (수동 숫자 입력 무시)
            pass
        elif lat is not None and lon is not None:
            # 2. 지도 마커는 그대로인데 숫자를 입력/수정했다면 숫자로 Point 갱신
            cleaned_data['point'] = Point(lon, lat, srid=4326)

        # 만약 지도도 안 찍고 숫자도 안 적었다면 에러 발생
        if not cleaned_data.get('point'):
            self.add_error('point', '지도를 클릭하거나 위도/경도 숫자를 반드시 입력해야 합니다.')

        return cleaned_data


# 2. LocationAdmin에 Form 적용
@admin.register(Location)
class LocationAdmin(GISModelAdmin):
    form = LocationAdminForm  # 위에서 만든 폼 적용

    # 폼 화면에 보여질 필드 순서 (이름 -> 위도 -> 경도 -> 지도)
    fields = ('name', 'latitude', 'longitude', 'point')

    list_display = ('name', 'display_coordinates', 'created_at')
    search_fields = ('name',)

    gis_widget_kwargs = {
        'attrs': {
            'default_zoom': 7,
            'default_lon': 127.0,
            'default_lat': 37.0,
        }
    }

    def display_coordinates(self, obj):
        if obj.point:
            return f"Lat: {obj.point.y}, Lon: {obj.point.x}"
        return "-"

    display_coordinates.short_description = '좌표 (위도, 경도)'


# WeeklyEnvironmentDataAdmin은 이전 코드 그대로 유지
@admin.register(WeeklyEnvironmentData)
class WeeklyEnvironmentDataAdmin(admin.ModelAdmin):
    list_display = ('location', 'start_date', 'end_date', 'ta', 'p', 'sdwi', 'created_at')
    list_filter = ('location', 'start_date')
    search_fields = ('location__name',)
    date_hierarchy = 'start_date'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('기본 정보', {'fields': ('location', 'start_date', 'end_date')}),
        ('기상 데이터 (ERA5)', {'fields': ('ws', 'ta', 'ts_1', 'ts_2', 'g', 'pa', 'p', 'vpd', 'netrad')}),
        ('위성 데이터 (Sentinel-1)', {'fields': ('vv', 'vh', 'sdwi')}),
        ('메타 정보', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )