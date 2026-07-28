from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import WeeklyEnvironmentData
from .services import predict_ch4_for_instance

class ModelPredictionTestAPIView(APIView):
    permission_classes = [AllowAny, ]

    def get(self, request, env_id):
        env_object = get_object_or_404(WeeklyEnvironmentData, id=env_id)
        prediction = predict_ch4_for_instance(env_object)
        return Response({'value': prediction}, status=status.HTTP_200_OK)


