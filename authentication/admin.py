from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import FCUser

@admin.register(FCUser)
class FCUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'nickname', 'is_admin', 'is_staff')
    
    fieldsets = UserAdmin.fieldsets + (
        ('추가 정보', {'fields': ('nickname', 'is_admin')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('추가 정보', {'fields': ('nickname', 'is_admin')}),
    )

    list_filter = ('is_admin', 'is_staff', 'is_active')