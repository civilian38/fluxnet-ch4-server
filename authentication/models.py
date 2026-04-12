from django.contrib.auth.models import AbstractUser
from django.db import models

class FCUser(AbstractUser):
    nickname = models.CharField(max_length=20, null=False, blank=True)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        if self.nickname:
            return self.nickname
        return self.username