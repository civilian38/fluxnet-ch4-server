from django.db import models

class Location(models.Model):
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} ({self.latitude}, {self.longitude})'

class CH4Data(models.Model):
    date = models.DateField()
    prediction = models.FloatField(default=0.0)
    description = models.TextField(default="")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='ch4_data_set')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.location.name} | {self.date}'

    class Meta:
        ordering = ['-date']