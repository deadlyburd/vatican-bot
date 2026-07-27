"""
Google Sheets integration — read bookings, write payment links, lookup status.

Uses gspread with a Google service account for authentication.
The sheet must be shared with the service account email as Editor.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials

from agent.config import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class Booking:
    """A single booking row from the Master sheet."""
    row: int                      # 1-indexed row number in the sheet
    booking_id: str               # Column G
    date: str                     # Column A (YYYY-MM-DD or DD/MM/YYYY)
    time: str                     # Column B (HH:MM)
    product: str                  # Column C
    pax: int                      # Column D
    first_name: str               # Column E
    last_name: str                # Column F
    status: str                   # Column H
    confirmation: str             # Column I
    payment_link: str             # Column J
    missing_info: str             # Column K
    ticket_type: str              # Column L
    platform: str                 # Column M

    @property
    def has_payment_link(self) -> bool:
        """Check if this booking already has a payment URL."""
        return bool(self.payment_link) and "epay" in self.payment_link.lower()

    @property
    def is_pending(self) -> bool:
        """Check if this booking needs tickets booked."""
        if self.has_payment_link:
            return False
        if "CANCEL" in (self.status or "").upper():
            return False
        return True


# ── Sheet Client ────────────────────────────────────────────────────────────

class SheetsClient:
    """Read/write Google Sheets for the booking pipeline."""

    def __init__(self):
        self._client: gspread.Client | None = None
        self._sheet: gspread.Spreadsheet | None = None

    # ── Connection ──────────────────────────────────────────────────────

    @property
    def client(self) -> gspread.Client:
        if self._client is None:
            creds = Credentials.from_service_account_file(
                config.google_service_account_file,
                scopes=SCOPES,
            )
            self._client = gspread.authorize(creds)
            logger.info("Google Sheets: authorized via service account")
        return self._client

    @property
    def sheet(self) -> gspread.Spreadsheet:
        if self._sheet is None:
            self._sheet = self.client.open_by_key(config.google_sheet_id)
            logger.info(
                "Google Sheets: opened sheet %s (tabs: %s)",
                config.google_sheet_id[:20],
                [w.title for w in self._sheet.worksheets()],
            )
        return self._sheet

    # ── Read ────────────────────────────────────────────────────────────

    def get_master_bookings(self) -> List[Booking]:
        """
        Read the Master sheet and return all bookings needing action.

        The Master sheet has these columns:
            A=Date, B=Time, C=Product, D=Pax, E=First Name, F=Last Name,
            G=Booking ID, H=Status, I=Confirmation, J=Payment Link,
            K=Missing Info, L=Ticket Type, M=Platform
        """
        try:
            ws = self.sheet.worksheet(config.master_sheet)
        except gspread.WorksheetNotFound:
            logger.warning("Master sheet '%s' not found", config.master_sheet)
            return []

        rows = ws.get_all_values()
        if len(rows) < 2:
            logger.info("Master sheet is empty (no data rows)")
            return []

        headers = [h.strip().lower() for h in rows[0]]
        logger.info("Master sheet: %d data rows, headers=%s", len(rows) - 1, headers[:5])

        bookings = []
        for i, row in enumerate(rows[1:], start=2):  # 1-indexed, skip header
            if len(row) < 13:
                continue  # Skip incomplete rows

            b = Booking(
                row=i,
                date=(row[0] or "").strip(),
                time=(row[1] or "").strip(),
                product=(row[2] or "").strip(),
                pax=self._parse_int(row[3]),
                first_name=(row[4] or "").strip(),
                last_name=(row[5] or "").strip(),
                booking_id=(row[6] or "").strip(),
                status=(row[7] or "").strip(),
                confirmation=(row[8] or "").strip(),
                payment_link=(row[9] or "").strip(),
                missing_info=(row[10] or "").strip(),
                ticket_type=(row[11] or "").strip(),
                platform=(row[12] or "").strip() if len(row) > 12 else "",
            )

            # Skip rows without key data
            if not b.first_name or not b.last_name:
                continue
            if not b.date:
                continue

            # Skip past dates
            try:
                d = self._parse_date(b.date)
                if d and d < date.today():
                    continue
            except (ValueError, IndexError):
                pass

            bookings.append(b)

        logger.info("Master sheet: %d actionable bookings found", len(bookings))
        return bookings

    def get_pending_bookings(self) -> List[Booking]:
        """Return only bookings that still need tickets (no payment link yet)."""
        all_bookings = self.get_master_bookings()
        pending = [b for b in all_bookings if b.is_pending]
        logger.info(
            "Master sheet: %d total, %d pending (need booking)",
            len(all_bookings), len(pending),
        )
        return pending

    # ── Write ───────────────────────────────────────────────────────────

    def write_payment_link(self, booking: Booking, epay_url: str) -> bool:
        """
        Write the payment link to column J (Payment Link) for a booking.

        Returns True on success, False on failure.
        """
        try:
            ws = self.sheet.worksheet(config.master_sheet)
            ws.update_cell(booking.row, 10, epay_url)  # Column J = 10
            logger.info(
                "Sheet: wrote payment link for %s %s (row %d)",
                booking.first_name, booking.last_name, booking.row,
            )
            return True
        except Exception as e:
            logger.error("Sheet: failed to write payment link: %s", e)
            return False

    def write_status(self, booking: Booking, status: str) -> bool:
        """Write booking status to column H."""
        try:
            ws = self.sheet.worksheet(config.master_sheet)
            ws.update_cell(booking.row, 8, status)  # Column H = 8
            return True
        except Exception as e:
            logger.error("Sheet: failed to write status: %s", e)
            return False

    # ── Lookup (for customer bot) ───────────────────────────────────────

    def lookup_booking(self, booking_id: str) -> Optional[Booking]:
        """Find a booking by its ID. Returns None if not found."""
        for b in self.get_master_bookings():
            if b.booking_id == booking_id:
                return b
        return None

    def lookup_by_email(self, email: str) -> List[Booking]:
        """Find bookings by customer email (searches Bookings sheet)."""
        try:
            ws = self.sheet.worksheet(config.bookings_sheet)
        except gspread.WorksheetNotFound:
            return []

        rows = ws.get_all_values()
        if len(rows) < 2:
            return []

        headers = [h.strip().lower() for h in rows[0]]
        email_col = None
        for i, h in enumerate(headers):
            if "email" in h:
                email_col = i
                break

        if email_col is None:
            return []

        results = []
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > email_col and row[email_col].strip().lower() == email.lower():
                # Build a minimal Booking from the Bookings sheet data
                results.append(Booking(
                    row=i,
                    booking_id=self._col(row, headers, "bookingid"),
                    date=self._col(row, headers, "activitydate") or self._col(row, headers, "date"),
                    time=self._col(row, headers, "starttime") or self._col(row, headers, "time"),
                    product=self._col(row, headers, "producttitle") or "",
                    pax=self._parse_int(self._col(row, headers, "totalparticipants")),
                    first_name=self._col(row, headers, "customerfirstname") or "",
                    last_name=self._col(row, headers, "customerlastname") or "",
                    status=self._col(row, headers, "status") or "",
                    confirmation=self._col(row, headers, "confirmationcode") or "",
                    payment_link=self._col(row, headers, "paymentlink") or "",
                    missing_info="",
                    ticket_type="",
                    platform="",
                ))
        return results

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_int(value: str) -> int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _parse_date(value: str) -> date | None:
        """Try multiple date formats."""
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _col(row: List[str], headers: List[str], key: str) -> str:
        """Get a column value by header key (case-insensitive match)."""
        key = key.lower()
        for i, h in enumerate(headers):
            if h.strip().lower() == key and i < len(row):
                return row[i].strip()
        return ""


# ── Singleton ────────────────────────────────────────────────────────────────

_client: SheetsClient | None = None


def get_sheets() -> SheetsClient:
    global _client
    if _client is None:
        _client = SheetsClient()
    return _client
