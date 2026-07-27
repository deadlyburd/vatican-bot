from django.contrib import admin
from .models import Agency, MonitorTask, CheckResult

@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ('name', 'api_key', 'created_at')
    search_fields = ('name',)

@admin.register(MonitorTask)
class MonitorTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'agency', 'site', 'area_name', 'is_active', 'last_status', 'last_checked')
    list_filter = ('site', 'is_active', 'last_status', 'agency')
    search_fields = ('area_name',)
    readonly_fields = ('last_checked', 'last_status', 'last_result_summary')

@admin.register(CheckResult)
class CheckResultAdmin(admin.ModelAdmin):
    list_display = ('task', 'check_time', 'status')
    list_filter = ('status', 'check_time')
    readonly_fields = ('check_time', 'status', 'details', 'error_message', 'screenshot_path')
