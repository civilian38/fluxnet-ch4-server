from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .serializers import FCUserRegisterSerializer, FCUserInformationSerializer
from .models import FCUser

class FCUserRegisterView(CreateAPIView):
    queryset = FCUser.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = FCUserRegisterSerializer

class FCUserInfoView(RetrieveAPIView):
    permission_classes = [IsAuthenticated, ]
    serializer_class = FCUserInformationSerializer

    def get_object(self):
        return self.request.user