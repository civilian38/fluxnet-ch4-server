from django.contrib.gis.db import models

class Location(models.Model):
    name = models.CharField(max_length=100)
    point = models.PointField(srid=4326, spatial_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.point.y}, {self.point.x})"

    def get_coordinates(self):
        return self.point.y, self.point.x

class WeeklyEnvironmentData(models.Model):
    # Location 테이블과의 1:N 관계 설정
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='weekly_data')
    
    # 시간 정보
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)

    # --- 기상 데이터 (ERA5) ---
    ws = models.FloatField(help_text="풍속 (m/s)")
    ta = models.FloatField(help_text="기온 (Celsius)")
    ts_1 = models.FloatField(help_text="지표면 온도 (Celsius)")
    ts_2 = models.FloatField(help_text="토양 온도 (Celsius)")
    g = models.FloatField(help_text="지중열류량 (W/m^2)")
    pa = models.FloatField(help_text="지표면 기압 (kPa)")
    p = models.FloatField(help_text="총 강수량 (mm)")
    vpd = models.FloatField(help_text="대기차 건조도 (hPa)")
    netrad = models.FloatField(help_text="순 복사량 (W/m^2)")

    # --- 위성 데이터 (Sentinel-1) ---
    vv = models.FloatField(help_text="VV 편파 평균")
    vh = models.FloatField(help_text="VH 편파 평균")
    sdwi = models.FloatField(help_text="수분 지수 (SDWI)")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 동일한 장소에 동일한 시작일의 데이터가 중복 저장되는 것을 방지
        unique_together = ('location', 'start_date')
        # 시간순 조회를 위한 정렬 기준
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.location} | {self.start_date} ~ {self.end_date}"