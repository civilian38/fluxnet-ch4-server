from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny
from .serializers import FCUserRegisterSerializer
from .models import FCUser

class FCUserRegisterView(CreateAPIView):
    queryset = FCUser.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = FCUserRegisterSerializer