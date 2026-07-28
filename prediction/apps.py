import os
import joblib
from django.apps import AppConfig
from django.conf import settings

class PredictionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'prediction'
    
    # 모델을 담을 전역 변수
    ml_model = None

    def ready(self):
        # Django 서버가 시작될 때 한 번만 실행됨
        # (마이그레이션 등에서도 실행될 수 있으니 파일 존재 여부 확인 필수)
        model_path = os.path.join(settings.BASE_DIR, 'ml_models', 'ch4_prediction_model.joblib')
        
        if os.path.exists(model_path) and self.ml_model is None:
            self.ml_model = joblib.load(model_path)
            print("CH4 예측 모델 로드 완료!")