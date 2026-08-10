from datetime import datetime
from celery import shared_task

from .services import update_ch4_for_locations

@shared_task
def ch4_weekly_update():
    today = datetime.today()
    update_ch4_for_locations(today)
    return "Weekly Update Completed"