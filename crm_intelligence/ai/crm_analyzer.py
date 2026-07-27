"""
AI CRM Intelligence Layer
==========================
Uses AI to analyze CRM data and extract useful insights.
Filters noise, identifies patterns, and feeds intelligence to:
- Customer care bot (personalization)
- Admin dashboard (analytics)
- Booking engine (demand prediction)
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


@dataclass
class CRMInsight:
    """A single insight extracted from CRM data."""
    category: str  # "booking_pattern", "customer_behavior", "product_trend", "revenue", "operational"
    title: str
    description: str
    confidence: float  # 0.0 to 1.0
    data: Dict[str, Any] = field(default_factory=dict)
    action_required: bool = False
    priority: str = "medium"  # "low", "medium", "high", "critical"


@dataclass
class CustomerProfile:
    """AI-enriched customer profile."""
    email: str
    name: str
    total_bookings: int = 0
    total_passengers: int = 0
    total_spent: float = 0.0
    favorite_products: List[str] = field(default_factory=list)
    booking_frequency: str = "new"  # "new", "occasional", "regular", "vip"
    preferred_times: List[str] = field(default_factory=list)
    preferred_group_size: int = 0
    languages: List[str] = field(default_factory=list)
    countries_visited_from: List[str] = field(default_factory=list)
    last_booking_date: Optional[date] = None
    next_likely_booking: Optional[str] = None  # predicted product type
    satisfaction_estimate: str = "unknown"  # "low", "medium", "high", "unknown"
    tags: List[str] = field(default_factory=list)


@dataclass
class DemandForecast:
    """Predicted demand for a product/date range."""
    product_id: str
    product_title: str
    date: str
    predicted_demand: str  # "low", "medium", "high", "very_high"
    confidence: float
    factors: List[str] = field(default_factory=list)


class CRMAnalyzer:
    """AI-powered CRM data analyzer."""

    def __init__(self, bookings: List[Dict], activities: List[Dict],
                 passengers: List[Dict], products: List[Dict]):
        self.bookings = bookings
        self.activities = activities
        self.passengers = passengers
        self.products = products
        self._customer_cache = {}

    def analyze_all(self) -> List[CRMInsight]:
        """Run all analysis and return insights."""
        insights = []

        # Booking pattern analysis
        insights.extend(self._analyze_booking_patterns())

        # Customer behavior analysis
        insights.extend(self._analyze_customer_behavior())

        # Product trend analysis
        insights.extend(self._analyze_product_trends())

        # Revenue analysis
        insights.extend(self._analyze_revenue())

        # Operational insights
        insights.extend(self._analyze_operational())

        # Sort by confidence
        insights.sort(key=lambda x: x.confidence, reverse=True)

        logger.info(f"Generated {len(insights)} CRM insights")
        return insights

    def get_customer_profile(self, email: str) -> Optional[CustomerProfile]:
        """Build an AI-enriched profile for a specific customer."""
        customer_bookings = [b for b in self.bookings
                           if b.get("customerEmail", "").lower() == email.lower()]
        if not customer_bookings:
            return None

        first = customer_bookings[0]
        profile = CustomerProfile(
            email=email,
            name=f"{first.get('customerFirstName', '')} {first.get('customerLastName', '')}".strip(),
            total_bookings=len(customer_bookings),
        )

        # Get activities for this customer's bookings
        booking_ids = {b.get("bookingId", "") for b in customer_bookings}
        customer_activities = [a for a in self.activities
                             if a.get("bookingId", "") in booking_ids]

        # Get passengers
        customer_passengers = [p for p in self.passengers
                             if p.get("bookingId", "") in booking_ids]

        profile.total_passengers = len(customer_passengers)

        # Favorite products
        product_counts = Counter(a.get("productTitle", "") for a in customer_activities)
        profile.favorite_products = [p for p, c in product_counts.most_common(5) if p]

        # Preferred times
        time_counts = Counter(a.get("startTime", "") for a in customer_activities if a.get("startTime"))
        profile.preferred_times = [t for t, c in time_counts.most_common(3)]

        # Preferred group size
        sizes = [int(a.get("totalParticipants", 0) or 0) for a in customer_activities if a.get("totalParticipants")]
        if sizes:
            profile.preferred_group_size = max(set(sizes), key=sizes.count)

        # Booking frequency
        if profile.total_bookings >= 10:
            profile.booking_frequency = "vip"
        elif profile.total_bookings >= 5:
            profile.booking_frequency = "regular"
        elif profile.total_bookings >= 2:
            profile.booking_frequency = "occasional"
        else:
            profile.booking_frequency = "new"

        # Languages and countries
        profile.languages = list(set(
            b.get("customerLanguage", "") for b in customer_bookings if b.get("customerLanguage")
        ))
        profile.countries_visited_from = list(set(
            b.get("customerCountry", "") for b in customer_bookings if b.get("customerCountry")
        ))

        # Last booking date
        dates = []
        for a in customer_activities:
            try:
                d = datetime.strptime(a.get("activityDate", ""), "%Y-%m-%d").date()
                dates.append(d)
            except (ValueError, TypeError):
                continue
        if dates:
            profile.last_booking_date = max(dates)

        # Generate tags
        profile.tags = self._generate_customer_tags(profile, customer_activities)

        # Next likely booking prediction
        profile.next_likely_booking = self._predict_next_booking(profile)

        return profile

    def get_useful_info_for_bot(self, customer_email: str) -> Dict[str, Any]:
        """
        Extract ONLY the useful info from CRM that the customer care bot needs.
        This filters out noise and returns clean, actionable data.
        """
        profile = self.get_customer_profile(customer_email)
        if not profile:
            return {"found": False}

        # Get upcoming bookings
        booking_ids = {b.get("bookingId", "") for b in self.bookings
                       if b.get("customerEmail", "").lower() == customer_email.lower()}
        upcoming = []
        today = date.today()

        for a in self.activities:
            if a.get("bookingId", "") in booking_ids:
                try:
                    activity_date = datetime.strptime(a.get("activityDate", ""), "%Y-%m-%d").date()
                    if activity_date >= today:
                        upcoming.append({
                            "date": a.get("activityDate", ""),
                            "time": a.get("startTime", ""),
                            "product": a.get("productTitle", ""),
                            "participants": a.get("totalParticipants", 0),
                            "status": a.get("status", ""),
                            "confirmation": a.get("productConfirmationCode", ""),
                            "is_vatican": "vatican" in a.get("productTitle", "").lower() or "sistine" in a.get("productTitle", "").lower(),
                            "is_colosseum": "colosseum" in a.get("productTitle", "").lower(),
                            "has_audio_guide": "audio" in a.get("productTitle", "").lower(),
                            "pickup": a.get("pickupTitle", "") if a.get("pickupTitle", "") != "FALSE" else None,
                        })
                except (ValueError, TypeError):
                    continue

        # Sort by date
        upcoming.sort(key=lambda x: x.get("date", ""))

        return {
            "found": True,
            "name": profile.name,
            "booking_frequency": profile.booking_frequency,
            "total_bookings": profile.total_bookings,
            "favorite_products": profile.favorite_products[:3],
            "preferred_group_size": profile.preferred_group_size,
            "preferred_times": profile.preferred_times,
            "language": profile.languages[0] if profile.languages else "en",
            "country": profile.countries_visited_from[0] if profile.countries_visited_from else "",
            "upcoming_bookings": upcoming[:10],
            "tags": profile.tags,
            "next_likely_interest": profile.next_likely_booking,
            "is_vip": profile.booking_frequency in ("regular", "vip"),
        }

    def _generate_customer_tags(self, profile: CustomerProfile,
                                 activities: List[Dict]) -> List[str]:
        """Generate descriptive tags for a customer."""
        tags = []

        # Frequency tags
        if profile.booking_frequency == "vip":
            tags.append("💎 VIP Customer")
        elif profile.booking_frequency == "regular":
            tags.append("🔄 Regular Customer")

        # Product interest tags
        product_types = Counter()
        for a in activities:
            title = a.get("productTitle", "").lower()
            if "vatican" in title or "sistine" in title:
                product_types["Vatican"] += 1
            if "colosseum" in title:
                product_types["Colosseum"] += 1
            if "private" in title:
                product_types["Private Tour"] += 1
            if "group" in title:
                product_types["Group Tour"] += 1

        for ptype, count in product_types.most_common(3):
            tags.append(f"🏛️ {ptype} ({count}x)")

        # Group size tags
        if profile.preferred_group_size >= 6:
            tags.append("👨‍👩‍👧‍👦 Large Group")
        elif profile.preferred_group_size >= 3:
            tags.append("👥 Family/Group")
        elif profile.preferred_group_size == 2:
            tags.append("💑 Couple")
        elif profile.preferred_group_size == 1:
            tags.append("🚶 Solo Traveler")

        # Time preference tags
        if profile.preferred_times:
            hour = int(profile.preferred_times[0].split(":")[0])
            if hour < 10:
                tags.append("🌅 Early Bird")
            elif hour >= 15:
                tags.append("🌆 Afternoon Visitor")

        return tags

    def _predict_next_booking(self, profile: CustomerProfile) -> str:
        """Predict what the customer might book next."""
        if not profile.favorite_products:
            return "Vatican Museums guided tour"

        # Simple prediction based on patterns
        if "Vatican" in profile.favorite_products[0]:
            if profile.preferred_group_size >= 4:
                return "Private Vatican tour for group"
            return "Vatican Museums skip-the-line"

        if profile.preferred_group_size <= 2:
            return "Private walking tour of Rome"

        return "Full day Rome tour"

    def _analyze_booking_patterns(self) -> List[CRMInsight]:
        """Analyze booking patterns."""
        insights = []

        # Popular booking dates
        date_counts = Counter()
        for a in self.activities:
            if a.get("activityDate"):
                date_counts[a["activityDate"]] += 1

        # Popular times
        time_counts = Counter()
        for a in self.activities:
            if a.get("startTime"):
                hour = a["startTime"].split(":")[0]
                time_counts[f"{hour}:00"] += 1

        top_times = time_counts.most_common(5)
        if top_times:
            insights.append(CRMInsight(
                category="booking_pattern",
                title="Most Popular Tour Times",
                description=f"Peak booking hours: {', '.join(f'{t[0]} ({t[1]} bookings)' for t in top_times[:3])}",
                confidence=0.85,
                data={"top_times": top_times},
            ))

        # Popular products
        product_counts = Counter()
        for a in self.activities:
            if a.get("productTitle"):
                product_counts[a["productTitle"]] += 1

        top_products = product_counts.most_common(5)
        if top_products:
            insights.append(CRMInsight(
                category="product_trend",
                title="Top Selling Products",
                description=f"Most booked: {', '.join(p[0][:50] for p in top_products[:3])}",
                confidence=0.9,
                data={"top_products": top_products},
            ))

        # Channel distribution
        channel_counts = Counter(b.get("channelTitle", "Unknown") for b in self.bookings)
        total = len(self.bookings)
        if total > 0:
            channel_dist = {k: f"{v/total*100:.1f}%" for k, v in channel_counts.most_common(5)}
            insights.append(CRMInsight(
                category="booking_pattern",
                title="Booking Channel Distribution",
                description=f"Channels: {', '.join(f'{k}: {v}' for k, v in list(channel_dist.items())[:3])}",
                confidence=0.95,
                data={"channels": channel_dist},
            ))

        return insights

    def _analyze_customer_behavior(self) -> List[CRMInsight]:
        """Analyze customer behavior patterns."""
        insights = []

        # Repeat vs new customers
        email_counts = Counter(b.get("customerEmail", "") for b in self.bookings)
        repeat = sum(1 for c in email_counts.values() if c > 1)
        total_unique = len(email_counts)

        if total_unique > 0:
            repeat_rate = repeat / total_unique * 100
            insights.append(CRMInsight(
                category="customer_behavior",
                title=f"Repeat Customer Rate: {repeat_rate:.1f}%",
                description=f"{repeat} repeat customers out of {total_unique} unique customers",
                confidence=0.95,
                data={"repeat_rate": repeat_rate, "repeat_count": repeat, "total_unique": total_unique},
            ))

        # Group size distribution
        group_sizes = []
        for a in self.activities:
            try:
                size = int(a.get("totalParticipants", 0) or 0)
                if size > 0:
                    group_sizes.append(size)
            except (ValueError, TypeError):
                continue

        if group_sizes:
            avg_size = sum(group_sizes) / len(group_sizes)
            size_dist = Counter(group_sizes)
            insights.append(CRMInsight(
                category="customer_behavior",
                title=f"Average Group Size: {avg_size:.1f}",
                description=f"Most common group size: {size_dist.most_common(1)[0][0]} people. "
                           f"Distribution: {dict(size_dist.most_common(5))}",
                confidence=0.85,
                data={"avg_size": avg_size, "distribution": dict(size_dist.most_common(10))},
            ))

        return insights

    def _analyze_product_trends(self) -> List[CRMInsight]:
        """Analyze product trends."""
        insights = []

        # Vatican vs Colosseum split
        vatican_count = sum(1 for a in self.activities
                          if "vatican" in a.get("productTitle", "").lower()
                          or "sistine" in a.get("productTitle", "").lower())
        colosseum_count = sum(1 for a in self.activities
                            if "colosseum" in a.get("productTitle", "").lower())
        total = len(self.activities)

        if total > 0:
            insights.append(CRMInsight(
                category="product_trend",
                title="Product Category Split",
                description=f"Vatican: {vatican_count/total*100:.1f}%, "
                           f"Colosseum: {colosseum_count/total*100:.1f}%, "
                           f"Other: {(total-vatican_count-colosseum_count)/total*100:.1f}%",
                confidence=0.95,
                data={"vatican": vatican_count, "colosseum": colosseum_count, "total": total},
            ))

        # Price range analysis
        prices = []
        for p in self.products:
            try:
                price = float(p.get("priceFrom", 0) or 0)
                if price > 0:
                    prices.append(price)
            except (ValueError, TypeError):
                continue

        if prices:
            avg_price = sum(prices) / len(prices)
            min_price = min(prices)
            max_price = max(prices)
            insights.append(CRMInsight(
                category="product_trend",
                title=f"Price Range: €{min_price:.0f} - €{max_price:.0f}",
                description=f"Average product price: €{avg_price:.0f}. "
                           f"{len(prices)} products in catalog.",
                confidence=0.9,
                data={"avg": avg_price, "min": min_price, "max": max_price, "count": len(prices)},
            ))

        return insights

    def _analyze_revenue(self) -> List[CRMInsight]:
        """Analyze revenue patterns."""
        insights = []

        # Paid vs unpaid
        paid_count = sum(1 for b in self.bookings
                        if b.get("paymentType", "") == "PAID_IN_FULL")
        total = len(self.bookings)

        if total > 0:
            insights.append(CRMInsight(
                category="revenue",
                title=f"Payment Rate: {paid_count/total*100:.1f}%",
                description=f"{paid_count} paid bookings out of {total} total",
                confidence=0.95,
                data={"paid": paid_count, "total": total},
            ))

        return insights

    def _analyze_operational(self) -> List[CRMInsight]:
        """Analyze operational insights."""
        insights = []

        # Upcoming bookings (next 7 days)
        today = date.today()
        next_week = today + timedelta(days=7)
        upcoming = []

        for a in self.activities:
            try:
                activity_date = datetime.strptime(a.get("activityDate", ""), "%Y-%m-%d").date()
                if today <= activity_date <= next_week:
                    upcoming.append(a)
            except (ValueError, TypeError):
                continue

        if upcoming:
            # Group by date
            by_date = defaultdict(int)
            for a in upcoming:
                by_date[a.get("activityDate", "")] += int(a.get("totalParticipants", 0) or 0)

            busiest_date = max(by_date.items(), key=lambda x: x[1]) if by_date else ("N/A", 0)
            insights.append(CRMInsight(
                category="operational",
                title=f"Next 7 Days: {len(upcoming)} activities, {sum(by_date.values())} participants",
                description=f"Busiest day: {busiest_date[0]} ({busiest_date[1]} participants)",
                confidence=0.95,
                data={"total_activities": len(upcoming), "total_participants": sum(by_date.values()),
                      "by_date": dict(by_date)},
                action_required=len(upcoming) > 50,
                priority="high" if len(upcoming) > 100 else "medium",
            ))

        # Cancellation rate
        cancelled = sum(1 for b in self.bookings if b.get("status", "") == "CANCELLED")
        total = len(self.bookings)
        if total > 0:
            cancel_rate = cancelled / total * 100
            insights.append(CRMInsight(
                category="operational",
                title=f"Cancellation Rate: {cancel_rate:.1f}%",
                description=f"{cancelled} cancelled out of {total} bookings",
                confidence=0.95,
                data={"cancelled": cancelled, "rate": cancel_rate},
                action_required=cancel_rate > 10,
                priority="high" if cancel_rate > 20 else "medium",
            ))

        return insights
