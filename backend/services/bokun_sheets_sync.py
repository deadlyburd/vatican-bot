"""
Bokun → Google Sheets Synchronization Service

This service syncs client bookings from Bokun to Google Sheets in real-time.
The bot then reads from this sheet to automatically complete Vatican ticket bookings.

Flow:
1. Bokun webhook → This service
2. Service writes to Google Sheets
3. Bot reads from Google Sheets
4. Bot monitors Vatican and books tickets
5. Bot updates Google Sheets with booking status
"""

import logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from typing import Dict, List, Optional
import os

logger = logging.getLogger(__name__)

# Google Sheets API configuration
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Your Google Sheets API Key and Sheet URL
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
SHEET_URL = os.getenv('GOOGLE_SHEET_URL', '')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '')


class BokunSheetsSync:
    """
    Synchronizes Bokun bookings to Google Sheets
    """
    
    def __init__(self):
        self.client = None
        self.sheet = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Google Sheets client"""
        try:
            # Try service account first (recommended for production)
            service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', '/app/google_credentials.json')
            
            if os.path.exists(service_account_file):
                creds = Credentials.from_service_account_file(
                    service_account_file,
                    scopes=SCOPES
                )
                self.client = gspread.authorize(creds)
                logger.info("✅ Google Sheets client initialized with service account")
            else:
                # Fallback: Use API key for read-only access
                # Note: API key alone won't allow writes, need service account
                logger.warning("⚠️ Service account file not found. Using API key (read-only)")
                # For write access, you MUST use service account
                raise Exception("Service account required for write access")
            
            # Open the sheet
            self.sheet = self.client.open_by_key(SHEET_ID)
            logger.info(f"✅ Connected to Google Sheet: {self.sheet.title}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            raise
    
    def add_booking_from_bokun(self, bokun_data: Dict) -> bool:
        """
        Add a new booking from Bokun to Google Sheets
        
        Args:
            bokun_data: Dictionary containing Bokun booking data
            
        Expected bokun_data format:
        {
            'booking_id': 'BK12345',
            'date': '15/06/2026',
            'time': '10:00',
            'visitors': 2,
            'ticket_type': 'Vatican Museums - Standard Entry',
            'customer': {
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john@example.com',
                'phone': '+393331234567'
            },
            'participants': [
                {
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'birth_date': '01/01/1990',
                    'gender': 'M'
                },
                {
                    'first_name': 'Jane',
                    'last_name': 'Doe',
                    'birth_date': '15/05/1992',
                    'gender': 'F'
                }
            ],
            'status': 'Pending',
            'created_at': '2026-05-26T10:30:00Z'
        }
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the "Bookings_Input" worksheet (where Bokun writes)
            try:
                worksheet = self.sheet.worksheet('Bookings_Input')
            except gspread.exceptions.WorksheetNotFound:
                # Create worksheet if it doesn't exist
                worksheet = self.sheet.add_worksheet(title='Bookings_Input', rows=1000, cols=20)
                # Add headers
                headers = [
                    'Booking ID', 'Date', 'Time', 'Visitors', 'Ticket Type',
                    'First Name', 'Last Name', 'Email', 'Phone',
                    'Status', 'Created At', 'Notes'
                ]
                worksheet.append_row(headers)
                logger.info("✅ Created 'Bookings_Input' worksheet with headers")
            
            # Extract customer data
            customer = bokun_data.get('customer', {})
            
            # Prepare row data
            row = [
                bokun_data.get('booking_id', ''),
                bokun_data.get('date', ''),
                bokun_data.get('time', ''),
                bokun_data.get('visitors', 1),
                bokun_data.get('ticket_type', 'Vatican Museums - Standard Entry'),
                customer.get('first_name', ''),
                customer.get('last_name', ''),
                customer.get('email', ''),
                customer.get('phone', ''),
                bokun_data.get('status', 'Pending'),
                bokun_data.get('created_at', datetime.now().isoformat()),
                bokun_data.get('notes', '')
            ]
            
            # Append row to sheet
            worksheet.append_row(row)
            logger.info(f"✅ Added booking {bokun_data.get('booking_id')} to Google Sheets")
            
            # Also add participants to "Participants" worksheet
            self._add_participants(bokun_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add booking to Google Sheets: {e}")
            return False
    
    def _add_participants(self, bokun_data: Dict):
        """Add participants to Participants worksheet"""
        try:
            # Get or create Participants worksheet
            try:
                worksheet = self.sheet.worksheet('Participants')
            except gspread.exceptions.WorksheetNotFound:
                worksheet = self.sheet.add_worksheet(title='Participants', rows=1000, cols=10)
                headers = [
                    'Booking ID', 'Participant #', 'First Name', 'Last Name',
                    'Birth Date', 'Gender', 'Email', 'Phone', 'Notes'
                ]
                worksheet.append_row(headers)
                logger.info("✅ Created 'Participants' worksheet with headers")
            
            booking_id = bokun_data.get('booking_id', '')
            participants = bokun_data.get('participants', [])
            
            for idx, participant in enumerate(participants, start=1):
                row = [
                    booking_id,
                    idx,
                    participant.get('first_name', ''),
                    participant.get('last_name', ''),
                    participant.get('birth_date', ''),
                    participant.get('gender', ''),
                    participant.get('email', ''),
                    participant.get('phone', ''),
                    participant.get('notes', '')
                ]
                worksheet.append_row(row)
            
            logger.info(f"✅ Added {len(participants)} participants for booking {booking_id}")
            
        except Exception as e:
            logger.error(f"Failed to add participants: {e}")
    
    def get_pending_bookings(self) -> List[Dict]:
        """
        Get all pending bookings from Google Sheets
        
        Returns:
            List of booking dictionaries
        """
        try:
            worksheet = self.sheet.worksheet('Bookings_Input')
            records = worksheet.get_all_records()
            
            # Filter only pending bookings
            pending = [
                record for record in records
                if record.get('Status', '').lower() == 'pending'
            ]
            
            logger.info(f"✅ Found {len(pending)} pending bookings")
            return pending
            
        except Exception as e:
            logger.error(f"Failed to get pending bookings: {e}")
            return []
    
    def update_booking_status(self, booking_id: str, status: str, 
                            payment_link: str = None, notes: str = None):
        """
        Update booking status in Google Sheets
        
        Args:
            booking_id: Booking ID to update
            status: New status (e.g., 'Monitoring', 'Available', 'Booked', 'Completed')
            payment_link: Optional payment link
            notes: Optional notes
        """
        try:
            # Update in Bookings_Input
            worksheet = self.sheet.worksheet('Bookings_Input')
            
            # Find the row with this booking_id
            cell = worksheet.find(booking_id)
            if cell:
                row = cell.row
                
                # Update status column (column 10)
                worksheet.update_cell(row, 10, status)
                
                # Update notes if provided
                if notes:
                    worksheet.update_cell(row, 12, notes)
                
                logger.info(f"✅ Updated booking {booking_id} status to {status}")
            
            # Also update in Bookings_Output worksheet
            self._update_output_sheet(booking_id, status, payment_link, notes)
            
        except Exception as e:
            logger.error(f"Failed to update booking status: {e}")
    
    def _update_output_sheet(self, booking_id: str, status: str, 
                           payment_link: str = None, notes: str = None):
        """Update or create entry in Bookings_Output worksheet"""
        try:
            # Get or create Bookings_Output worksheet
            try:
                worksheet = self.sheet.worksheet('Bookings_Output')
            except gspread.exceptions.WorksheetNotFound:
                worksheet = self.sheet.add_worksheet(title='Bookings_Output', rows=1000, cols=10)
                headers = [
                    'Booking ID', 'Date', 'Time', 'Status', 'Payment Link',
                    'Booked At', 'Marked', 'Notes'
                ]
                worksheet.append_row(headers)
                logger.info("✅ Created 'Bookings_Output' worksheet with headers")
            
            # Find existing row or create new
            try:
                cell = worksheet.find(booking_id)
                row = cell.row
                
                # Update existing row
                worksheet.update_cell(row, 4, status)  # Status
                if payment_link:
                    worksheet.update_cell(row, 5, payment_link)  # Payment Link
                if notes:
                    worksheet.update_cell(row, 8, notes)  # Notes
                
                # If status is 'Completed', add checkmark
                if status.lower() == 'completed':
                    worksheet.update_cell(row, 7, '✓')  # Marked
                    # Add green background
                    worksheet.format(f'A{row}:H{row}', {
                        'backgroundColor': {
                            'red': 0.7,
                            'green': 0.9,
                            'blue': 0.7
                        }
                    })
                
            except gspread.exceptions.CellNotFound:
                # Create new row
                row = [
                    booking_id,
                    '',  # Date (will be filled by bot)
                    '',  # Time (will be filled by bot)
                    status,
                    payment_link or '',
                    datetime.now().strftime('%Y-%m-%d %H:%M'),
                    '✓' if status.lower() == 'completed' else '',
                    notes or ''
                ]
                worksheet.append_row(row)
            
            logger.info(f"✅ Updated output sheet for booking {booking_id}")
            
        except Exception as e:
            logger.error(f"Failed to update output sheet: {e}")
    
    def mark_booking_completed(self, booking_id: str):
        """
        Mark booking as completed (add checkmark and green background)
        """
        self.update_booking_status(
            booking_id=booking_id,
            status='Completed',
            notes='Booking completed and paid'
        )


# Singleton instance
_bokun_sync = None

def get_bokun_sync() -> BokunSheetsSync:
    """Get or create BokunSheetsSync instance"""
    global _bokun_sync
    if _bokun_sync is None:
        _bokun_sync = BokunSheetsSync()
    return _bokun_sync


# Example usage
if __name__ == '__main__':
    # Test the service
    sync = get_bokun_sync()
    
    # Example: Add a booking from Bokun
    test_booking = {
        'booking_id': 'BK12345',
        'date': '15/06/2026',
        'time': '10:00',
        'visitors': 2,
        'ticket_type': 'Vatican Museums - Standard Entry',
        'customer': {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'phone': '+393331234567'
        },
        'participants': [
            {
                'first_name': 'John',
                'last_name': 'Doe',
                'birth_date': '01/01/1990',
                'gender': 'M'
            },
            {
                'first_name': 'Jane',
                'last_name': 'Doe',
                'birth_date': '15/05/1992',
                'gender': 'F'
            }
        ],
        'status': 'Pending',
        'created_at': datetime.now().isoformat()
    }
    
    # Add booking
    success = sync.add_booking_from_bokun(test_booking)
    print(f"Booking added: {success}")
    
    # Get pending bookings
    pending = sync.get_pending_bookings()
    print(f"Pending bookings: {len(pending)}")
    
    # Update status
    sync.update_booking_status('BK12345', 'Monitoring', notes='Bot is monitoring Vatican')
