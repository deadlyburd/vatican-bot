"""
Google Sheets Service
Imports participant names from Google Sheets and manages booking status
"""
import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Optional
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


class GoogleSheetsService:
    def __init__(self):
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Google Sheets client"""
        try:
            # Option 1: Service Account (Recommended)
            service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', '/app/google_credentials.json')
            
            if os.path.exists(service_account_file):
                creds = Credentials.from_service_account_file(
                    service_account_file,
                    scopes=SCOPES
                )
                self.client = gspread.authorize(creds)
                logger.info("✅ Google Sheets client initialized with service account")
            else:
                logger.warning("⚠️ Google service account file not found - Google Sheets integration disabled")
                
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
    
    def get_participants_from_sheet(self, sheet_url: str, sheet_name: str = 'Vatican_Participants') -> List[Dict]:
        """
        Get participants from Google Sheet
        
        Args:
            sheet_url: Google Sheets URL or ID
            sheet_name: Name of the worksheet (default: Vatican_Participants)
        
        Returns:
            List of participant dictionaries
        """
        try:
            if not self.client:
                logger.error("Google Sheets client not initialized")
                return []
            
            # Extract sheet ID from URL if needed
            sheet_id = self._extract_sheet_id(sheet_url)
            
            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            # Get all records (assumes first row is header)
            records = worksheet.get_all_records()
            
            # Convert to participant format
            participants = []
            for record in records:
                participant = {
                    'first_name': record.get('First Name', '').strip(),
                    'last_name': record.get('Last Name', '').strip(),
                    'email': record.get('Email', '').strip(),
                    'phone': record.get('Phone', '').strip(),
                    'birth_date': record.get('Birth Date', '').strip(),
                    'gender': record.get('Gender', 'M').strip().upper(),
                    'notes': record.get('Notes', '').strip()
                }
                
                # Only add if has name
                if participant['first_name'] and participant['last_name']:
                    participants.append(participant)
            
            logger.info(f"✅ Loaded {len(participants)} participants from Google Sheet")
            return participants
            
        except Exception as e:
            logger.error(f"Error reading Google Sheet: {e}")
            return []
    
    def read_bookings_input(self, sheet_url: str, sheet_name: str = 'Bookings_Input') -> List[Dict]:
        """
        Read pending bookings from input sheet (Bokun writes here)
        Returns list of booking dictionaries
        """
        try:
            if not self.client:
                return []
            
            sheet_id = self._extract_sheet_id(sheet_url)
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            records = worksheet.get_all_records()
            
            # Filter only pending bookings
            bookings = []
            for record in records:
                if record.get('Status', '').lower() == 'pending':
                    bookings.append({
                        'booking_id': record.get('Booking ID', ''),
                        'date': record.get('Date', ''),
                        'time': record.get('Time', ''),
                        'visitors': int(record.get('Visitors', 1)),
                        'first_name': record.get('First Name', ''),
                        'last_name': record.get('Last Name', ''),
                        'email': record.get('Email', ''),
                        'phone': record.get('Phone', ''),
                    })
            
            logger.info(f"✅ Read {len(bookings)} pending bookings from sheet")
            return bookings
            
        except Exception as e:
            logger.error(f"Error reading bookings input: {e}")
            return []
    
    def write_booking_result(self, sheet_url: str, booking_id: str, 
                            status: str, payment_link: str = None,
                            sheet_name: str = 'Bookings_Output'):
        """
        Write booking result to output sheet
        """
        try:
            if not self.client:
                return False
            
            sheet_id = self._extract_sheet_id(sheet_url)
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            # Find row with booking_id
            try:
                cell = worksheet.find(booking_id)
                row = cell.row
            except:
                # Add new row
                row = len(worksheet.get_all_values()) + 1
                worksheet.update_cell(row, 1, booking_id)
            
            # Update columns (adjust column numbers based on your sheet structure)
            worksheet.update_cell(row, 4, status)  # Status column
            if payment_link:
                worksheet.update_cell(row, 5, payment_link)  # Payment Link column
            worksheet.update_cell(row, 6, datetime.now().strftime('%Y-%m-%d %H:%M'))  # Booked At
            
            logger.info(f"✅ Updated booking {booking_id} in output sheet")
            return True
            
        except Exception as e:
            logger.error(f"Error writing booking result: {e}")
            return False
    
    def mark_booking_completed(self, sheet_url: str, booking_id: str,
                              sheet_name: str = 'Bookings_Output'):
        """
        Mark booking as completed (add checkmark and green background)
        """
        try:
            if not self.client:
                return False
            
            sheet_id = self._extract_sheet_id(sheet_url)
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            # Find row
            try:
                cell = worksheet.find(booking_id)
                row = cell.row
            except:
                logger.warning(f"Booking {booking_id} not found in sheet")
                return False
            
            # Add checkmark
            worksheet.update_cell(row, 7, '✓')  # Marked column
            
            # Add green background
            worksheet.format(f'A{row}:G{row}', {
                'backgroundColor': {
                    'red': 0.7,
                    'green': 0.9,
                    'blue': 0.7
                }
            })
            
            logger.info(f"✅ Marked booking {booking_id} as completed")
            return True
            
        except Exception as e:
            logger.error(f"Error marking booking completed: {e}")
            return False
    
    def check_if_booked(self, sheet_url: str, booking_id: str,
                       sheet_name: str = 'Bookings_Output') -> bool:
        """
        Check if booking is marked as completed in sheet
        """
        try:
            if not self.client:
                return False
            
            sheet_id = self._extract_sheet_id(sheet_url)
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            # Find row
            try:
                cell = worksheet.find(booking_id)
                row = cell.row
            except:
                return False
            
            marked = worksheet.cell(row, 7).value  # Marked column
            
            return marked == '✓'
            
        except Exception as e:
            logger.error(f"Error checking booking status: {e}")
            return False
    
    def get_participants_for_agency(self, agency_id: int) -> List[Dict]:
        """
        Get participants for a specific agency
        Looks up agency's Google Sheet URL from database
        """
        from monitors.models import Agency
        
        try:
            agency = Agency.objects.get(id=agency_id)
            
            # Check if agency has Google Sheet URL configured
            sheet_url = getattr(agency, 'google_sheet_url', None)
            
            if not sheet_url:
                logger.warning(f"Agency {agency.name} has no Google Sheet URL configured")
                return []
            
            return self.get_participants_from_sheet(sheet_url)
            
        except Agency.DoesNotExist:
            logger.error(f"Agency {agency_id} not found")
            return []
        except Exception as e:
            logger.error(f"Error getting participants for agency: {e}")
            return []
    
    def _extract_sheet_id(self, sheet_url: str) -> str:
        """Extract sheet ID from URL"""
        if 'docs.google.com' in sheet_url:
            return sheet_url.split('/d/')[1].split('/')[0]
        return sheet_url


# Singleton instance
_sheets_service = None

def get_sheets_service() -> GoogleSheetsService:
    """Get or create Google Sheets service instance"""
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = GoogleSheetsService()
    return _sheets_service
