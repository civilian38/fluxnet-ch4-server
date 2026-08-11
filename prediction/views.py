import datetime
from dateutil.relativedelta import relativedelta

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_gis.filters import InBBoxFilter

from django.utils import timezone
from django.db.models import F

from .serializers import (
    LocationMapSerializer, 
    LocationDetailSerializer, 
    LocationCreateSerializer,
    CH4TrendSerializer
)
from .permissions import IsAdminUserOrReadOnly
from .models import Location

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

    # /api/prediction/locations/{id}/ch4_trend/?months=3
    @action(detail=True, methods=['get'])
    def ch4_trend(self, request, pk=None):
        location = self.get_object()
        
        # 쿼리 파라미터에서 개월 수 받기 (기본값 3개월)
        months = int(request.query_params.get('months', 3))
        start_date_limit = timezone.now().date() - datetime.timedelta(days=30 * months)

        # 해당 기간의 데이터 조회 (prediction_value 테이블 조인 최적화)
        qs = location.weekly_data.filter(
            start_date__gte=start_date_limit,
            prediction_value__isnull=False # CH4 예측값이 있는 데이터만 필터링
        ).select_related('prediction_value')

        serializer = CH4TrendSerializer(qs, many=True)
        return Response(serializer.data)

    # /api/prediction/locations/{id}/environment_trend/
    @action(detail=True, methods=['get'])
    def environment_trend(self, request, pk=None):
        location = self.get_object()
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        fields_param = request.query_params.get('fields')

        today = timezone.now().date()
        
        if not end_date:
            end_date = today.strftime('%Y-%m-%d')
            end_date_obj = today
        else:
            end_date_obj = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()

        if not start_date:
            start_date_obj = end_date_obj - relativedelta(months=6)
            
            start_date = start_date_obj.strftime('%Y-%m-%d')

        allowed_fields = {
            'ws', 'ta', 'ts_1', 'ts_2', 'g', 'pa', 'p', 'vpd', 'netrad',
            'vv', 'vh', 'sdwi'
        }

        requested_fields = []
        include_ch4 = False

        if fields_param:
            requested_keys = [k.strip() for k in fields_param.split(',')]
            for key in requested_keys:
                if key in allowed_fields:
                    requested_fields.append(key)
                elif key == 'ch4_value':
                    include_ch4 = True
        else:
            # 필드 지정이 없으면 기본적으로 전체를 보냄
            requested_fields = list(allowed_fields)
            include_ch4 = True

        qs = location.weekly_data.all()

        if start_date:
            qs = qs.filter(start_date__gte=start_date)
        if end_date:
            qs = qs.filter(start_date__lte=end_date)

        annotations = {'date': F('start_date')}
        
        if include_ch4:
            annotations['ch4_value'] = F('prediction_value__value')

        # DB 레벨에서 키 이름 변경
        qs = qs.annotate(**annotations)

        values_keys = ['date'] + requested_fields
        if include_ch4:
            values_keys.append('ch4_value')

        # 그래프는 보통 과거->현재 (오름차순)으로 그려지므로 order_by('start_date') 적용
        data = list(qs.order_by('start_date').values(*values_keys))

        return Response(data)