from django.db import models
from django.utils import timezone
import hashlib
import secrets

class Agency(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('agency', 'Agency'),
    ]
    
    name = models.CharField(max_length=255)
    api_key = models.CharField(max_length=255, unique=True, blank=True, null=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True, null=True)
    owner_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, unique=True, help_text="Clerk User ID")
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    google_sheet_url = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Google Sheets URL for participant names"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Agencies"


class User(models.Model):
    """Simple user model for authentication"""
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True, db_index=True)
    password_hash = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255, blank=True)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name='users')
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    is_super_admin = models.BooleanField(default=False)  # New field for super admin
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    def set_password(self, raw_password):
        """Hash and set password"""
        salt = secrets.token_hex(16)
        password_with_salt = f"{raw_password}{salt}"
        self.password_hash = f"{salt}${hashlib.sha256(password_with_salt.encode()).hexdigest()}"

    def check_password(self, raw_password):
        """Verify password"""
        try:
            salt, hashed = self.password_hash.split('$')
            password_with_salt = f"{raw_password}{salt}"
            return hashlib.sha256(password_with_salt.encode()).hexdigest() == hashed
        except:
            return False

    def __str__(self):
        return f"{self.username} ({self.agency.name})"

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email'], name='users_email_idx'),
            models.Index(fields=['username'], name='users_username_idx'),
        ]


class SiteCredential(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name='credentials')
    site = models.CharField(max_length=50, choices=[('vatican', 'Vatican')])
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.site.upper()} Creds - {self.agency.name}"

class Proxy(models.Model):
    ip_port = models.CharField(max_length=255, help_text="e.g., 142.111.48.253:7030")
    username = models.CharField(max_length=255, blank=True, null=True)
    password = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    fail_count = models.PositiveIntegerField(default=0)
    consecutive_failures = models.PositiveIntegerField(default=0)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.ip_port
    
    class Meta:
        verbose_name_plural = "Proxies"

class MonitorTask(models.Model):
    SITE_CHOICES = [
        ('vatican', 'Vatican Museums'),
    ]
    
    TICKET_TYPE_CHOICES = [
        (0, 'Regular Ticket'),
        (1, 'Guided Tour'),
    ]

    MATCH_STRATEGY_CHOICES = [
        ('any', 'ANY (Notify if any slot matches)'),
        ('all', 'ALL (Notify only if all slots match)'),
    ]

    NOTIFICATION_MODE_CHOICES = [
        ('any_change', 'Notify on any change'),
        ('available_only', 'Notify only when available'),
        ('silent', 'Silent (No notifications)'),
    ]

    TIER_CHOICES = [
        ('notify', 'Notify Only'),
        ('hold', 'Notify + Hold'),
        ('snipe', 'Notify + Hold + Auto-Pay'),
    ]

    # ❌ REMOVED CHOICES - No longer used with extension:
    # - PAY_MODE_CHOICES: Extension always auto-pays
    # - CHECKOUT_METHOD_CHOICES: Extension always uses browser

    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name='tasks')
    site = models.CharField(max_length=50, choices=SITE_CHOICES)
    area_name = models.CharField(max_length=255, help_text="e.g., Musei Vaticani or Colosseo")
    dates = models.JSONField(help_text="List of dates to check (e.g., ['2026-06-15'])")
    preferred_times = models.JSONField(help_text="List of preferred times (e.g., ['10:00', '14:30'])")
    visitors = models.PositiveIntegerField(default=1)
    adult_count = models.PositiveIntegerField(default=1)
    child_count = models.PositiveIntegerField(default=0)
    ticket_type = models.IntegerField(choices=TICKET_TYPE_CHOICES, default=0)
    ticket_label = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. 'Standard Entry (Full Price)'") 
    
    # ✅ ENHANCED: Vatican-specific ticket selection
    ticket_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Vatican ticket ID (e.g., '929041748' from resolve_all_dynamic_ids). Leave empty to scan ALL tickets.",
        db_index=True  # For efficient grouping
    )
    ticket_name = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        help_text="Human-readable ticket name (e.g., 'Musei Vaticani - Biglietti d'ingresso')"
    )
    
    # ✅ ENHANCED: Language for guided tours
    language = models.CharField(
        max_length=10, 
        blank=True, 
        null=True,
        help_text="Language code for guided tours: ENG, ITA, FRA, TED, SPA. NULL for standard tickets that don't require language."
    )
    
    check_interval = models.IntegerField(default=60, help_text="Interval in seconds")
    
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='notify')
    # Participant names for snipe mode — set via /setparticipants before sniping
    # JSON list: [{"first_name": "John", "last_name": "Doe"}, ...]
    participants_json = models.TextField(blank=True, null=True,
        help_text="Participant names for snipe reservation (JSON list)")
    match_strategy = models.CharField(max_length=20, choices=MATCH_STRATEGY_CHOICES, default='any')
    notification_mode = models.CharField(max_length=20, choices=NOTIFICATION_MODE_CHOICES, default='any_change')
    
    is_active = models.BooleanField(default=True)
    last_checked = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=50, default='unknown')
    last_result_summary = models.TextField(blank=True, null=True)
    
    # ❌ REMOVED FIELDS - Extension handles these automatically:
    # - checkout_method: Extension always uses browser
    # - pay_mode: Extension always auto-pays
    # - remote_worker_needed: Extension handles this
    # - remote_worker_claimed: Extension handles this
    # - agent_target: Extension handles this
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.visitors = self.adult_count + self.child_count
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.site.upper()} Task - {self.agency.name} ({self.created_at.strftime('%Y-%m-%d')})"

class CheckResult(models.Model):
    task = models.ForeignKey(MonitorTask, on_delete=models.CASCADE, related_name='results')
    check_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=50) # available, sold_out, error
    details = models.JSONField(blank=True, null=True) # Detailed slot data
    error_message = models.TextField(blank=True, null=True)
    screenshot_path = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"Result for {self.task.id} at {self.check_time}"


class BuyerProfile(models.Model):
    """
    Stores real person details for snipe mode auto-booking.
    One profile per agency — used as representativeUser + participantUser.
    """
    agency = models.OneToOneField(Agency, on_delete=models.CASCADE, related_name='buyer_profile')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    country = models.CharField(max_length=100, default='Italy')
    city = models.CharField(max_length=100, default='Roma')
    birth_date = models.DateField(null=True, blank=True, help_text='YYYY-MM-DD')
    gender = models.CharField(max_length=1, default='M', choices=[('M','Male'),('F','Female')])
    language = models.CharField(max_length=5, default='en')
    # Card details for snipe auto-pay (stored encrypted in production)
    card_number = models.CharField(max_length=20, blank=True, null=True)
    card_expiry = models.CharField(max_length=7, blank=True, null=True, help_text='MM/YYYY')
    card_cvv = models.CharField(max_length=4, blank=True, null=True)
    card_holder = models.CharField(max_length=100, blank=True, null=True)
    # Participant list (JSON array of {first_name, last_name}) — uploaded via /setparticipants
    participants_json = models.TextField(blank=True, null=True, help_text='JSON list of participant names')

    class Meta:
        db_table = 'buyer_profiles'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.agency.name})"

    def to_representative_user(self):
        from datetime import datetime
        bd = None
        if self.birth_date:
            bd = datetime.combine(self.birth_date, datetime.min.time()).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        return {
            'name': self.first_name,
            'surname': self.last_name,
            'gender': self.gender,
            'country': self.country,
            'city': self.city,
            'birthDate': bd,
            'email': self.email,
            'confirmEmail': self.email,
            'telephoneNumber': self.phone,
            'language': self.language,
        }

    def to_participant_list(self, visitors, adult_count=None, child_count=None, ticket_id=60, service_ids=None):
        if adult_count is None:
            adult_count = visitors
        if child_count is None:
            child_count = 0
            
        if service_ids is None:
            service_ids = [58]
        # Use uploaded participant names if available, otherwise repeat representative
        import json
        names = []
        if self.participants_json:
            try:
                names = json.loads(self.participants_json)
            except Exception:
                names = []
        # Pad/trim to match visitor count
        while len(names) < visitors:
            names.append({'first_name': self.first_name, 'last_name': self.last_name})
        names = names[:visitors]
        out = []
        for p in names:
            if not isinstance(p, dict):
                p = {}
            first = (p.get('first_name') or p.get('name') or '').strip()
            last = (p.get('last_name') or p.get('surname') or '').strip()
            if not first:
                first = (self.first_name or '').strip()
            if not last:
                last = (self.last_name or '').strip()
            out.append({
                'name': first,
                'surname': last,
                'id': ticket_id if i < adult_count else 61, # 61 is Ridotto
                'ticketType': 'intero' if i < adult_count else 'ridotto',
                'services': service_ids,
            })
        return out


class HeldSlot(models.Model):
    """Tracks Vatican slots held via /api/visit/recap with active session keepalive."""
    STATUS_CHOICES = [
        ('held', 'Held'),
        ('paying', 'Paying'),
        ('paid', 'Paid'),
        ('released', 'Released'),
        ('expired', 'Expired'),
    ]

    task = models.ForeignKey(MonitorTask, on_delete=models.CASCADE, related_name='held_slots')
    date = models.CharField(max_length=20, help_text='DD/MM/YYYY')
    slot_id = models.CharField(max_length=50, help_text='e.g. 2026*8776')
    slot_time = models.CharField(max_length=10, help_text='e.g. 12:00')
    ticket_id = models.CharField(max_length=50)
    ticket_name = models.CharField(max_length=300)
    visitors = models.PositiveIntegerField(default=2)
    adult_count = models.PositiveIntegerField(default=2)
    child_count = models.PositiveIntegerField(default=0)
    total_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    jsessionid = models.CharField(max_length=255)
    ticketmv = models.CharField(max_length=50, blank=True, null=True)
    recap_id = models.CharField(max_length=50, blank=True, null=True, help_text='e.g. 2026/8367/119 — needed for reservation')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='held')
    hold_started_at = models.DateTimeField(default=timezone.now)
    last_keepalive_at = models.DateTimeField(default=timezone.now)
    released_at = models.DateTimeField(null=True, blank=True)
    payment_url = models.TextField(null=True, blank=True)
    payment_ready = models.BooleanField(default=False, help_text="User clicked Pay in Telegram, signal the worker to break hold and proceed.")
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'held_slots'
        ordering = ['-hold_started_at']

    def __str__(self):
        return f"Hold #{self.id} | {self.task.agency.name} | {self.date} {self.slot_time} | {self.status}"

    def hold_duration_minutes(self):
        return int((timezone.now() - self.hold_started_at).total_seconds() / 60)

    def hold_duration_hours(self):
        return int((timezone.now() - self.hold_started_at).total_seconds() / 3600)

    def hours_until_expiry(self):
        """Calculate hours remaining until 24-hour Vatican expiry"""
        return max(0, 24 - self.hold_duration_hours())

    def get_serverid(self):
        """Extract SERVERID from notes field"""
        try:
            data = json.loads(self.notes or '{}')
            return data.get('serverid', '')
        except Exception:
            return ''

    def get_jsessionid(self):
        """Get JSESSIONID from stored field"""
        return self.jsessionid or ''

    def get_ticketmv(self):
        """Get ticketmv from stored field"""
        return self.ticketmv or ''

    def is_session_fresh(self):
        """Check if session is fresh enough for reservation"""
        from django.core.cache import cache
        import time
        
        session_cache_key = f"vatican_session_fresh_{self.jsessionid[:16]}"
        session_created = cache.get(session_cache_key)
        
        if session_created:
            session_age = time.time() - session_created
            return session_age < 20 * 3600  # Less than 20 hours old
        
        return True  # Assume fresh if no cache data


class VaticanTask(models.Model):
    """
    Vatican booking task from Google Sheets
    Tracks automated booking workflow
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('checking', 'AI Checking'),
        ('awaiting_info', 'Awaiting Info'),
        ('ready', 'Ready for Booking'),
        ('booking', 'Booking in Progress'),
        ('booked', 'Booked'),
        ('verified', 'Verified'),
        ('tour_done', 'Tour Done'),
        ('review_sent', 'Review Sent'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    TICKET_TYPE_CHOICES = [
        (0, 'Standard Ticket'),
        (1, 'Guided Tour'),
    ]
    
    # Booking Info
    booking_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="Confirmation code from Google Sheets")
    target_date = models.DateField(help_text="Activity date")
    target_time = models.CharField(max_length=10, help_text="Preferred time (HH:MM)")
    visitors = models.PositiveIntegerField(default=1)
    ticket_type = models.IntegerField(choices=TICKET_TYPE_CHOICES, default=0)
    language = models.CharField(max_length=10, blank=True, null=True, help_text="Language code for guided tours (ENG, ITA, etc)")
    
    # Customer Info
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=50, blank=True, null=True)
    participants_data = models.JSONField(blank=True, null=True, help_text="Full participant details (JSON)")
    
    # Status & Workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.IntegerField(default=1, help_text="Higher = more urgent")
    missing_info = models.TextField(blank=True, null=True, help_text="AI-detected missing info")
    contact_log = models.JSONField(default=list, blank=True, help_text="Log of emails/messages sent")
    
    # Monitoring
    last_checked = models.DateTimeField(null=True, blank=True)
    available_slots = models.TextField(blank=True, null=True, help_text="Comma-separated available time slots")
    
    # Booking Result
    booked_time = models.CharField(max_length=10, blank=True, null=True, help_text="Actually booked time (HH:MM)")
    checkout_url = models.TextField(blank=True, null=True, help_text="Epay checkout URL")
    reference_code = models.CharField(max_length=100, blank=True, null=True, help_text="Vatican reference/order number")
    verification_data = models.JSONField(blank=True, null=True, help_text="Result of ticket verification")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'vatican_tasks'
        ordering = ['target_date', '-priority', 'created_at']
        indexes = [
            models.Index(fields=['booking_id'], name='vt_booking_id_idx'),
            models.Index(fields=['status'], name='vt_status_idx'),
            models.Index(fields=['target_date'], name='vt_target_date_idx'),
        ]
    
    def __str__(self):
        return f"{self.booking_id} - {self.target_date} - {self.status}"


class TelegramGroup(models.Model):
    """
    Represents a Telegram group/chat that has added the bot.
    Requires admin approval before receiving notifications.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]
    
    # Telegram Info
    chat_id = models.CharField(max_length=255, unique=True, db_index=True)
    chat_type = models.CharField(max_length=20)  # 'group', 'supergroup', 'channel', 'private'
    chat_title = models.CharField(max_length=255, null=True, blank=True)
    chat_username = models.CharField(max_length=255, null=True, blank=True)
    
    # Linked Agency (optional - for multi-agency support)
    agency = models.ForeignKey(Agency, on_delete=models.SET_NULL, null=True, blank=True, related_name='telegram_groups')
    
    # Approval Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.CharField(max_length=255, null=True, blank=True)  # Admin user ID
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    
    # Metadata
    added_by_user_id = models.CharField(max_length=255, null=True, blank=True)
    added_by_username = models.CharField(max_length=255, null=True, blank=True)
    added_by_first_name = models.CharField(max_length=255, null=True, blank=True)
    member_count = models.IntegerField(null=True, blank=True)
    
    # Settings
    notification_enabled = models.BooleanField(default=True)
    notification_language = models.CharField(max_length=10, default='en')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'telegram_groups'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.chat_title or self.chat_id} ({self.status})"
    
    def is_approved(self):
        return self.status == 'approved'
    
    def approve(self, admin_id):
        self.status = 'approved'
        self.approved_by = admin_id
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self, admin_id, reason=None):
        self.status = 'rejected'
        self.approved_by = admin_id
        self.rejection_reason = reason
        self.save()
    
    def suspend(self, reason=None):
        self.status = 'suspended'
        self.rejection_reason = reason
        self.save()


class BulkHoldConfig(models.Model):
    """
    Configuration for bulk slot locking.
    Scans a date range and recaps every available slot matching the time window.
    Recap = server-side lock for ~55 min. Keepalive re-recaps every 25 min.
    No Turnstile needed — only required when completing a reservation.
    """
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name='bulk_hold_configs')
    # Date range (inclusive), stored as YYYY-MM-DD
    date_from = models.DateField(help_text='Start date (inclusive)')
    date_to = models.DateField(help_text='End date (inclusive)')
    # Time window to lock (e.g. 08:30 to 14:30)
    time_from = models.CharField(max_length=5, default='08:00', help_text='HH:MM')
    time_to = models.CharField(max_length=5, default='17:00', help_text='HH:MM')
    # Visitors per slot
    visitors = models.PositiveIntegerField(default=2)
    adult_count = models.PositiveIntegerField(default=2)
    child_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Stats
    target_total = models.PositiveIntegerField(default=10, help_text="Goal: total tickets to hold across all slots")
    total_locked = models.IntegerField(default=0)
    last_scan_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'bulk_hold_configs'
        ordering = ['-created_at']

    def __str__(self):
        return (f"BulkHold #{self.id} | {self.agency.name} | "
                f"{self.date_from}→{self.date_to} | {self.time_from}-{self.time_to} | "
                f"{self.visitors}v | {'active' if self.is_active else 'paused'}")

    def date_range(self):
        """Yield all dates in range as DD/MM/YYYY strings."""
        from datetime import timedelta
        current = self.date_from
        while current <= self.date_to:
            yield current.strftime('%d/%m/%Y')
            current += timedelta(days=1)

    def time_in_window(self, time_str: str) -> bool:
        """Check if a HH:MM time is within the configured window."""
        return self.time_from <= time_str <= self.time_to
