from django.contrib import admin
from .models import Location, CH4Data

# 1. Location 상세 페이지 하단에서 CH4Data를 바로 편집할 수 있게 설정
class CH4DataInline(admin.TabularInline):
    model = CH4Data
    extra = 1  # 기본으로 표시할 빈 입력 칸 개수
    fields = ['date', 'prediction', 'description']

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    # 목록(List) 화면에 표시될 필드
    list_display = ('name', 'latitude', 'longitude', 'created_at')
    
    # 검색 기능 (이름으로 검색)
    search_fields = ('name',)
    
    # 상세 페이지에 CH4Data 입력 폼 포함
    inlines = [CH4DataInline]

@admin.register(CH4Data)
class CH4DataAdmin(admin.ModelAdmin):
    # 목록 화면에 표시될 필드
    list_display = ('location', 'date', 'prediction', 'created_at')
    
    # 필터 기능 (날짜 및 위치별로 필터링)
    list_filter = ('date', 'location')
    
    # 검색 기능 (위치 이름 또는 설명으로 검색)
    # 외래키 필드는 'location__name'과 같이 언더바 2개(__)를 사용합니다.
    search_fields = ('location__name', 'description')
    
    # 날짜별로 계층 구조 탐색 가능 (상단에 날짜 선택바 생성)
    date_hierarchy = 'date'
    
    # 데이터가 많아질 경우 위치 선택을 드롭다운 대신 검색식으로 변경 (권장)
    # 이를 위해 LocationAdmin에 search_fields가 설정되어 있어야 합니다.
    autocomplete_fields = ['location']