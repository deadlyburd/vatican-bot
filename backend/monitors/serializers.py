from rest_framework import serializers
from .models import Agency, MonitorTask, CheckResult, Proxy, SiteCredential, User

class SiteCredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteCredential
        fields = '__all__'

class ProxySerializer(serializers.ModelSerializer):
    class Meta:
        model = Proxy
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    agency_name = serializers.ReadOnlyField(source='agency.name')
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'full_name', 'agency', 'agency_name', 
                 'is_active', 'is_admin', 'is_super_admin', 'last_login', 'created_at']
        read_only_fields = ['id', 'created_at', 'last_login']

class AgencySerializer(serializers.ModelSerializer):
    credentials = SiteCredentialSerializer(many=True, read_only=True)
    task_limit = serializers.SerializerMethodField()

    class Meta:
        model = Agency
        fields = ['id', 'name', 'api_key', 'telegram_chat_id', 'credentials', 'created_at', 'plan', 'task_limit']

    def get_task_limit(self, obj):
        limits = {'free': 2, 'pro': 20, 'agency': 500}
        return limits.get(obj.plan, 2)

class CheckResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckResult
        fields = '__all__'

class MonitorTaskSerializer(serializers.ModelSerializer):
    agency_name = serializers.ReadOnlyField(source='agency.name')
    latest_check = serializers.SerializerMethodField()
    slots_found = serializers.SerializerMethodField()
    target_date = serializers.SerializerMethodField()
    
    class Meta:
        model = MonitorTask
        fields = '__all__'
    
    def get_target_date(self, obj):
        """Get the first date from dates JSON field"""
        if obj.dates and isinstance(obj.dates, list) and len(obj.dates) > 0:
            return obj.dates[0]
        return None
    
    def get_slots_found(self, obj):
        """Get number of slots from latest check result"""
        latest_result = obj.results.order_by('-check_time').first()
        if latest_result and latest_result.details:
            # Check if details has slots
            if isinstance(latest_result.details, dict):
                slots = latest_result.details.get('slots', [])
                if isinstance(slots, list):
                    return len(slots)
            elif isinstance(latest_result.details, list):
                return len(latest_result.details)
        return 0
    
    def get_latest_check(self, obj):
        """Get the most recent CheckResult with slots for this task."""
        latest_result = obj.results.order_by('-check_time').first()
        if latest_result:
            return {
                'id': latest_result.id,
                'check_time': latest_result.check_time,
                'status': latest_result.status,
                'slots_found': self.get_slots_found(obj),
                'details': latest_result.details,
                'error_message': latest_result.error_message
            }
        return None
