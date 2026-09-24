from django.contrib import admin

from .models import ActivityLog, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'object_type', 'object_id', 'ip_address')
    list_filter = ('action',)
    search_fields = ('user__username', 'description', 'object_type', 'object_id')
    ordering = ('-created_at',)
    readonly_fields = [f.name for f in ActivityLog._meta.fields]
