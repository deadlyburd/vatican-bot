"""
CRM Sync Service
=================
Periodically syncs data from Google Sheets CRM.
Provides cached access to parsed customer, booking, and product data.
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from crm_intelligence.parsers.sheet_parser import SheetParser, Booking, ActivityLine, Product, Customer
from crm_intelligence.ai.crm_analyzer import CRMAnalyzer, CRMInsight

logger = logging.getLogger(__name__)


class CRMSyncService:
    """
    Singleton service that keeps CRM data in sync.
    Runs in background thread, refreshes at configured interval.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.parser = None
        self.analyzer = None

        # Cached data
        self.bookings: List[Booking] = []
        self.activities: List[ActivityLine] = []
        self.products: List[Product] = []
        self.customers: List[Customer] = []
        self.passengers: List[Any] = []
        self.insights: List[CRMInsight] = []

        # Metadata
        self.last_sync: Optional[datetime] = None
        self.last_sync_duration: float = 0
        self.sync_count: int = 0
        self.last_error: Optional[str] = None
        self.is_syncing: bool = False

        self._initialized = True

    def initialize(self, sheet_id: str, credentials_file: str, refresh_interval: int = 300):
        """Initialize the sync service."""
        self.parser = SheetParser(sheet_id=sheet_id, credentials_file=credentials_file)
        self.refresh_interval = refresh_interval

        # Do initial sync
        self.sync_now()

        # Start background thread
        self._start_background_sync()

    def _start_background_sync(self):
        """Start the background sync thread."""
        thread = threading.Thread(target=self._sync_loop, daemon=True, name="crm-sync")
        thread.start()
        logger.info(f"CRM sync background thread started (interval: {self.refresh_interval}s)")

    def _sync_loop(self):
        """Background sync loop."""
        while True:
            time.sleep(self.refresh_interval)
            try:
                self.sync_now()
            except Exception as e:
                logger.error(f"Background CRM sync failed: {e}")
                self.last_error = str(e)

    def sync_now(self):
        """Force an immediate sync."""
        if self.is_syncing:
            logger.warning("Sync already in progress, skipping")
            return

        self.is_syncing = True
        start = time.time()

        try:
            logger.info("Starting CRM sync...")
            self.parser.connect()

            # Parse all data
            self.bookings = self.parser.parse_bookings()
            self.activities = self.parser.parse_activity_lines()
            self.products = self.parser.parse_products()
            self.customers = self.parser.parse_customers()

            # Build analyzer
            bookings_dict = [
                {
                    "bookingId": b.booking_id,
                    "customerEmail": b.customer.email if b.customer else "",
                    "customerFirstName": b.customer.first_name if b.customer else "",
                    "customerLastName": b.customer.last_name if b.customer else "",
                    "status": b.status.value,
                    "channelTitle": str(b.channel_title),
                    "paymentType": b.payment_type,
                }
                for b in self.bookings
            ]
            activities_dict = [
                {
                    "bookingId": a.booking_id,
                    "productTitle": a.product_title,
                    "activityDate": a.activity_date,
                    "startTime": a.startTime,
                    "totalParticipants": a.total_participants,
                    "status": a.status,
                    "productConfirmationCode": a.product_confirmation_code,
                }
                for a in self.activities
            ]

            self.analyzer = CRMAnalyzer(bookings_dict, activities_dict, [], [])

            # Generate insights
            self.insights = self.analyzer.analyze_all()

            self.last_sync = datetime.now()
            self.sync_count += 1
            self.last_error = None
            self.last_sync_duration = time.time() - start

            logger.info(
                f"CRM sync #{self.sync_count} complete in {self.last_sync_duration:.1f}s: "
                f"{len(self.bookings)} bookings, {len(self.activities)} activities, "
                f"{len(self.products)} products, {len(self.customers)} customers, "
                f"{len(self.insights)} insights"
            )

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"CRM sync failed: {e}")
            raise
        finally:
            self.is_syncing = False

    def get_customer_info(self, email: str) -> Optional[Dict[str, Any]]:
        """Get useful info for a customer (for bot or dashboard)."""
        if not self.analyzer:
            return None
        return self.analyzer.get_useful_info_for_bot(email)

    def get_customer_profile(self, email: str) -> Optional[Any]:
        """Get full customer profile."""
        if not self.analyzer:
            return None
        return self.analyzer.get_customer_profile(email)

    def get_insights(self, category: str = None, priority: str = None) -> List[CRMInsight]:
        """Get AI insights, optionally filtered."""
        result = self.insights
        if category:
            result = [i for i in result if i.category == category]
        if priority:
            result = [i for i in result if i.priority == priority]
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get CRM stats."""
        emails = set(b.customer.email for b in self.bookings if b.customer and b.customer.email)
        return {
            "total_bookings": len(self.bookings),
            "total_activities": len(self.activities),
            "total_products": len(self.products),
            "unique_customers": len(emails),
            "total_insights": len(self.insights),
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_sync_duration": self.last_sync_duration,
            "sync_count": self.sync_count,
            "last_error": self.last_error,
            "is_syncing": self.is_syncing,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get full status for dashboard."""
        return {
            "stats": self.get_stats(),
            "insights": [
                {
                    "category": i.category,
                    "title": i.title,
                    "description": i.description,
                    "confidence": i.confidence,
                    "priority": i.priority,
                    "action_required": i.action_required,
                }
                for i in self.insights
            ],
        }


# Global instance
crm_service = CRMSyncService()
