"""
Google Sheets CRM Parser
========================
Parses and normalizes data from the Google Sheets CRM.
Handles the "viator data" sheet with all its worksheets.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date
from dataclasses import dataclass, field
from enum import Enum

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


class BookingStatus(Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    UNKNOWN = "UNKNOWN"


class ChannelType(Enum):
    VIATOR = "Viator.com"
    GETYOURGUIDE = "GetYourGuide"
    PROJECT_EXPEDITION = "Project Expedition"
    DIRECT = "Direct"
    OTHER = "Other"


@dataclass
class Customer:
    """Normalized customer from CRM."""
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    country: str = ""
    language: str = ""
    customer_id: str = ""
    accepts_marketing: bool = False

    # Derived
    full_name: str = ""
    is_repeat_customer: bool = False
    total_bookings: int = 0
    total_spent: float = 0.0

    def __post_init__(self):
        self.full_name = f"{self.first_name} {self.last_name}".strip()


@dataclass
class ActivityLine:
    """A single activity booking line."""
    booking_id: str
    confirmation_code: str
    activity_booking_id: str
    status: str
    product_id: str
    product_title: str
    activity_date: str
    startTime: str
    end_date_time: str
    total_participants: int
    rate_title: str
    barcode: str
    product_confirmation_code: str
    pickup_title: str
    dropoff_title: str
    guided_languages: str
    notes: str
    cancellation_policy: str
    seller_title: str
    customer_name: str

    # Derived
    is_vatican: bool = False
    is_colosseum: bool = False
    is_private: bool = False
    has_audio_guide: bool = False
    has_skip_the_line: bool = False
    price_estimate: float = 0.0


@dataclass
class Passenger:
    """A passenger on a booking."""
    booking_id: str
    confirmation_code: str
    activity_booking_id: str
    product_title: str
    activity_date: str
    start_time: str
    is_lead: bool = False
    pricing_category: str = ""
    ticket_category: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    date_of_birth: str = ""
    nationality: str = ""
    passport_id: str = ""
    gender: str = ""


@dataclass
class Product:
    """A tour/product offering."""
    product_id: str
    external_id: str
    title: str
    summary: str
    category: str
    location_code: str
    vendor_title: str
    duration_text: str
    base_language: str
    languages: str
    price_from: float
    key_photo_url: str
    review_rating: float
    review_count: int

    # Derived
    is_vatican: bool = False
    is_colosseum: bool = False
    is_private: bool = False
    is_group: bool = False
    has_gelato: bool = False
    has_audio_guide: bool = False
    has_skip_the_line: bool = False
    is_cruise_friendly: bool = False


@dataclass
class Booking:
    """A complete booking with all related data."""
    booking_id: str
    confirmation_code: str
    external_reference: str
    status: BookingStatus
    created_date: datetime
    payment_type: str
    seller_title: str
    seller_country: str
    channel_title: str
    channel_type: ChannelType
    activity_booking_count: int
    accepts_marketing: bool

    # Related data
    customer: Optional[Customer] = None
    activities: List[ActivityLine] = field(default_factory=list)
    passengers: List[Passenger] = field(default_factory=list)

    # Derived
    total_participants: int = 0
    total_activities: int = 0
    is_vatican: bool = False
    is_colosseum: bool = False
    is_confirmed: bool = False
    is_paid: bool = False
    is_cancelled: bool = False


class SheetParser:
    """Parses Google Sheets CRM data into normalized structures."""

    def __init__(self, sheet_id: str, credentials_file: str):
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self._client = None
        self._sheet = None
        self._cache = {}
        self._cache_timestamp = None

    def connect(self):
        """Connect to Google Sheets."""
        creds = Credentials.from_service_account_file(
            self.credentials_file, scopes=SCOPES
        )
        self._client = gspread.authorize(creds)
        self._sheet = self._client.open_by_key(self.sheet_id)
        logger.info(f"Connected to sheet: {self._sheet.title}")

    def _get_worksheet(self, name: str) -> gspread.Worksheet:
        """Get a worksheet by name."""
        if not self._sheet:
            self.connect()
        return self._sheet.worksheet(name)

    def _get_all_records(self, worksheet_name: str) -> List[Dict]:
        """Get all records from a worksheet as dicts."""
        ws = self._get_worksheet(worksheet_name)
        return ws.get_all_records()

    def parse_customers(self) -> List[Customer]:
        """Parse unique customers from Bookings sheet."""
        records = self._get_all_records("Bookings")
        customers = {}
        booking_counts = {}

        for row in records:
            email = row.get("customerEmail", "")
            if not email or email in customers:
                if email:
                    booking_counts[email] = booking_counts.get(email, 0) + 1
                continue

            customer = Customer(
                first_name=row.get("customerFirstName", ""),
                last_name=row.get("customerLastName", ""),
                email=email,
                phone=row.get("customerPhone", ""),
                country=row.get("customerCountry", ""),
                language=row.get("customerLanguage", ""),
                customer_id=row.get("customerId", ""),
                accepts_marketing=str(row.get("acceptsMarketing", "FALSE")).upper() == "TRUE",
            )
            customers[email] = customer
            booking_counts[email] = booking_counts.get(email, 0) + 1

        # Update booking counts
        for email, customer in customers.items():
            customer.total_bookings = booking_counts.get(email, 0)
            customer.is_repeat_customer = customer.total_bookings > 1

        result = list(customers.values())
        logger.info(f"Parsed {len(result)} unique customers from {len(records)} bookings")
        return result

    def parse_bookings(self, limit: int = None) -> List[Booking]:
        """Parse bookings from Bookings sheet."""
        records = self._get_all_records("Bookings")
        if limit:
            records = records[:limit]

        bookings = []
        for row in records:
            try:
                booking = Booking(
                    booking_id=row.get("bookingId", ""),
                    confirmation_code=row.get("confirmationCode", ""),
                    external_reference=row.get("externalBookingReference", ""),
                    status=BookingStatus(row.get("status", "UNKNOWN")),
                    created_date=self._parse_datetime(row.get("createdDate", "")),
                    payment_type=row.get("paymentType", ""),
                    seller_title=row.get("sellerTitle", ""),
                    seller_country=row.get("sellerCountry", ""),
                    channel_title=row.get("channelTitle", ""),
                    channel_type=self._detect_channel(row.get("channelTitle", "")),
                    activity_booking_count=int(row.get("activityBookingCount", 0) or 0),
                    accepts_marketing=str(row.get("acceptsMarketing", "FALSE")).upper() == "TRUE",
                )

                # Set derived fields
                booking.is_confirmed = booking.status == BookingStatus.CONFIRMED
                booking.is_paid = booking.payment_type == "PAID_IN_FULL"
                booking.is_cancelled = booking.status == BookingStatus.CANCELLED

                # Create customer
                booking.customer = Customer(
                    first_name=row.get("customerFirstName", ""),
                    last_name=row.get("customerLastName", ""),
                    email=row.get("customerEmail", ""),
                    phone=row.get("customerPhone", ""),
                    country=row.get("customerCountry", ""),
                    language=row.get("customerLanguage", ""),
                    customer_id=row.get("customerId", ""),
                )

                bookings.append(booking)
            except Exception as e:
                logger.warning(f"Error parsing booking row: {e}")
                continue

        logger.info(f"Parsed {len(bookings)} bookings")
        return bookings

    def parse_activity_lines(self, limit: int = None) -> List[ActivityLine]:
        """Parse activity lines from Activity_Lines sheet."""
        records = self._get_all_records("Activity_Lines")
        if limit:
            records = records[:limit]

        activities = []
        for row in records:
            try:
                activity = ActivityLine(
                    booking_id=row.get("bookingId", ""),
                    confirmation_code=row.get("confirmationCode", ""),
                    activity_booking_id=row.get("activityBookingId", ""),
                    status=row.get("status", ""),
                    product_id=row.get("productId", ""),
                    product_title=row.get("productTitle", ""),
                    activity_date=row.get("activityDate", ""),
                    startTime=row.get("startTime", ""),
                    end_date_time=row.get("endDateTime", ""),
                    total_participants=int(row.get("totalParticipants", 0) or 0),
                    rate_title=row.get("rateTitle", ""),
                    barcode=row.get("barcode", ""),
                    product_confirmation_code=row.get("productConfirmationCode", ""),
                    pickup_title=str(row.get("pickupTitle", "FALSE")),
                    dropoff_title=str(row.get("dropoffTitle", "FALSE")),
                    guided_languages=str(row.get("guidedLanguages", "")),
                    notes=row.get("notes", ""),
                    cancellation_policy=row.get("cancellationPolicy", ""),
                    seller_title=row.get("sellerTitle", ""),
                    customer_name=row.get("customerName", ""),
                )

                # Derive product features from title
                title_lower = activity.product_title.lower()
                activity.is_vatican = "vatican" in title_lower or "sistine" in title_lower
                activity.is_colosseum = "colosseum" in title_lower or "coliseum" in title_lower
                activity.is_private = "private" in title_lower
                activity.has_audio_guide = "audio" in title_lower
                activity.has_skip_the_line = "skip" in title_lower or "hosted entry" in title_lower

                activities.append(activity)
            except Exception as e:
                logger.warning(f"Error parsing activity line: {e}")
                continue

        logger.info(f"Parsed {len(activities)} activity lines")
        return activities

    def parse_passengers(self, limit: int = None) -> List[Passenger]:
        """Parse passengers from Passengers sheet."""
        records = self._get_all_records("Passengers")
        if limit:
            records = records[:limit]

        passengers = []
        for row in records:
            try:
                passenger = Passenger(
                    booking_id=row.get("bookingId", ""),
                    confirmation_code=row.get("confirmationCode", ""),
                    activity_booking_id=row.get("activityBookingId", ""),
                    product_title=row.get("productTitle", ""),
                    activity_date=row.get("activityDate", ""),
                    start_time=row.get("startTime", ""),
                    is_lead=str(row.get("leadPassenger", "FALSE")).upper() == "TRUE",
                    pricing_category=row.get("pricingCategory", ""),
                    ticket_category=row.get("ticketCategory", ""),
                    first_name=row.get("firstName", ""),
                    last_name=row.get("lastName", ""),
                    email=row.get("email", ""),
                    phone=row.get("phoneNumber", ""),
                    date_of_birth=row.get("dateOfBirth", ""),
                    nationality=row.get("nationality", ""),
                    passport_id=row.get("passportId", ""),
                    gender=row.get("gender", ""),
                )
                passengers.append(passenger)
            except Exception as e:
                logger.warning(f"Error parsing passenger: {e}")
                continue

        logger.info(f"Parsed {len(passengers)} passengers")
        return passengers

    def parse_products(self) -> List[Product]:
        """Parse products from Products sheet."""
        records = self._get_all_records("Products")
        products = []

        for row in records:
            try:
                title = row.get("title", "")
                summary = row.get("summary", "")
                title_lower = title.lower()
                summary_lower = summary.lower()

                product = Product(
                    product_id=row.get("productId", ""),
                    external_id=row.get("externalId", ""),
                    title=title,
                    summary=summary,
                    category=row.get("category", ""),
                    location_code=row.get("locationCode", ""),
                    vendor_title=row.get("vendorTitle", ""),
                    duration_text=row.get("durationText", ""),
                    base_language=row.get("baseLanguage", ""),
                    languages=row.get("languages", ""),
                    price_from=float(row.get("priceFrom", 0) or 0),
                    key_photo_url=row.get("keyPhotoUrl", ""),
                    review_rating=float(row.get("reviewRating", 0) or 0),
                    review_count=int(row.get("reviewCount", 0) or 0),
                )

                # Derive features
                product.is_vatican = "vatican" in title_lower or "sistine" in title_lower
                product.is_colosseum = "colosseum" in title_lower or "coliseum" in title_lower
                product.is_private = "private" in title_lower
                product.is_group = "group" in title_lower
                product.has_gelato = "gelato" in title_lower
                product.has_audio_guide = "audio" in title_lower
                product.has_skip_the_line = "skip" in title_lower
                product.is_cruise_friendly = "cruise" in title_lower

                products.append(product)
            except Exception as e:
                logger.warning(f"Error parsing product: {e}")
                continue

        logger.info(f"Parsed {len(products)} products")
        return products

    def get_customer_by_email(self, email: str) -> Optional[Dict]:
        """Look up a customer by email across all sheets."""
        bookings = self._get_all_records("Bookings")
        for row in bookings:
            if row.get("customerEmail", "").lower() == email.lower():
                return {
                    "first_name": row.get("customerFirstName", ""),
                    "last_name": row.get("customerLastName", ""),
                    "email": row.get("customerEmail", ""),
                    "phone": row.get("customerPhone", ""),
                    "country": row.get("customerCountry", ""),
                    "language": row.get("customerLanguage", ""),
                    "customer_id": row.get("customerId", ""),
                }
        return None

    def get_bookings_by_customer(self, email: str) -> List[Dict]:
        """Get all bookings for a customer by email."""
        bookings = self._get_all_records("Bookings")
        results = []
        for row in bookings:
            if row.get("customerEmail", "").lower() == email.lower():
                results.append(row)
        return results

    def get_upcoming_bookings(self, days_ahead: int = 30) -> List[Dict]:
        """Get bookings with activity dates in the next N days."""
        activities = self._get_all_records("Activity_Lines")
        today = date.today()
        results = []

        for row in activities:
            try:
                activity_date = datetime.strptime(
                    row.get("activityDate", ""), "%Y-%m-%d"
                ).date()
                delta = (activity_date - today).days
                if 0 <= delta <= days_ahead:
                    results.append(row)
            except (ValueError, TypeError):
                continue

        return results

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _detect_channel(self, channel_title: str) -> ChannelType:
        """Detect channel type from title."""
        title_lower = channel_title.lower()
        if "viator" in title_lower:
            return ChannelType.VIATOR
        elif "getyourguide" in title_lower:
            return ChannelType.GETYOURGUIDE
        elif "project expedition" in title_lower:
            return ChannelType.PROJECT_EXPEDITION
        elif "direct" in title_lower:
            return ChannelType.DIRECT
        return ChannelType.OTHER
