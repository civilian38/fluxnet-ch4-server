from rest_framework import serializers
from .models import FCUser

class FCUserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = FCUser
        fields = ('username', 'password', 'nickname', 'email')
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': False}, 
        }

    def create(self, validated_data):
        user = FCUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            nickname=validated_data.get('nickname', ''),
            is_admin=False
        )
        return user