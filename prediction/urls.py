from django.urls import path
from .views import ModelPredictionTestAPIView

urlpatterns = [
    # path('<int:env_id>/', ModelPredictionTestAPIView.as_view(), name='model-test'),
]