"""
Bokun API Integration

Fetches bookings directly from Bokun API and syncs to Google Sheets.
More reliable than webhooks as it polls Bokun every 5 minutes.

Bokun API Documentation: https://docs.bokun.io/
"""

import logging
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os

logger = logging.getLogger(__name__)

# Bokun API Credentials
BOKUN_ACCESS_KEY = os.getenv('BOKUN_ACCESS_KEY', '')
BOKUN_SECRET_KEY = os.getenv('BOKUN_SECRET_KEY', '')

# Bokun API Base URL
BOKUN_API_BASE = 'https://api.bokun.io'


class BokunAPI:
    """
    Bokun API Client
    
    Fetches bookings from Bokun and syncs to Google Sheets
    """
    
    def __init__(self, access_key: str = None, secret_key: str = None):
        """
        Initialize Bokun API client
        
        Args:
            access_key: Bokun access key (defaults to env var)
            secret_key: Bokun secret key (defaults to env var)
        """
        self.access_key = access_key or os.getenv('BOKUN_ACCESS_KEY', BOKUN_ACCESS_KEY)
        self.secret_key = secret_key or os.getenv('BOKUN_SECRET_KEY', BOKUN_SECRET_KEY)
        self.base_url = BOKUN_API_BASE
        
        logger.info(f"✅ Bokun API client initialized (Key: {self.access_key[:8]}...)")
    
    def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None, data: dict = None) -> dict:
        """
        Make authenticated request to Bokun API
        
        Args:
            endpoint: API endpoint (e.g., '/booking.json/booking-search')
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            data: Request body data
            
        Returns:
            Response JSON
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            # Bokun API uses custom headers for authentication
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-Bokun-AccessKey': self.access_key,
                    'X-Bokun-SecretKey': self.secret_key
                },
                timeout=30
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Bokun API HTTP error: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            raise
        except Exception as e:
            logger.error(f"Bokun API error: {e}")
            raise
    
    def get_confirmed_bookings(self, from_date: datetime = None, to_date: datetime = None) -> List[Dict]:
        """
        Get confirmed bookings from Bokun using booking-search endpoint
        
        Args:
            from_date: Start date (defaults to today)
            to_date: End date (defaults to 90 days from now)
            
        Returns:
            List of booking dictionaries
        """
        if not from_date:
            from_date = datetime.now()
        if not to_date:
            to_date = datetime.now() + timedelta(days=90)
        
        # Format dates for Bokun API (ISO format with time)
        from_str = from_date.strftime('%Y-%m-%dT00:00:00')
        to_str = to_date.strftime('%Y-%m-%dT23:59:59')
        
        logger.info(f"📥 Fetching Bokun bookings from {from_str} to {to_str}")
        
        all_bookings = []
        page = 0
        page_size = 100
        
        while True:
            try:
                # Bokun API uses POST /booking.json/booking-search with query body
                query = {
                    'startDateRange': {
                        'from': from_str,
                        'to': to_str,
                        'includeLower': True,
                        'includeUpper': True
                    },
                    'bookingStatuses': ['CONFIRMED'],
                    'page': page,
                    'pageSize': page_size
                }
                
                response = self._make_request(
                    endpoint='/booking.json/booking-search',
                    method='POST',
                    data=query
                )
                
                # The response might be a list of bookings or a dict containing a list
                if isinstance(response, list):
                    page_bookings = response
                elif isinstance(response, dict):
                    # Check for common list keys
                    page_bookings = response.get('results', []) or response.get('bookings', []) or []
                else:
                    page_bookings = []
                
                if not page_bookings:
                    break
                    
                all_bookings.extend(page_bookings)
                logger.info(f"📥 Page {page}: Fetched {len(page_bookings)} bookings (Total: {len(all_bookings)})")
                
                # If we got fewer than page_size, we reached the end
                if len(page_bookings) < page_size:
                    break
                    
                page += 1
                
            except Exception as e:
                logger.error(f"Failed to fetch Bokun bookings page {page}: {e}")
                break
                
        logger.info(f"✅ Fetched {len(all_bookings)} total bookings from Bokun")
        return all_bookings
    
    def get_booking_details(self, booking_id: str) -> Optional[Dict]:
        """
        Get detailed information for a specific booking
        
        Args:
            booking_id: Bokun booking ID
            
        Returns:
            Booking details dictionary
        """
        try:
            response = self._make_request(
                endpoint=f'/booking.json/booking/{booking_id}'
            )
            
            logger.info(f"✅ Fetched details for booking {booking_id}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to fetch booking {booking_id}: {e}")
            return None
    
    def parse_booking_for_sheets(self, booking: Dict) -> Dict:
        """
        Parse Bokun booking into format for Google Sheets
        
        Args:
            booking: Raw Bokun booking data from booking-search endpoint
            
        Returns:
            Formatted booking data for Google Sheets
        """
        try:
            # Extract booking ID from search result
            booking_id = booking.get('confirmationCode', '') or booking.get('id', '')
            
            # Extract product info - search results have product as BookingItemInfoDto
            product = booking.get('product', {})
            product_title = product.get('title', 'Vatican Museums - Standard Entry')
            
            # Extract date and time from startDate field
            start_date = booking.get('startDate')
            if start_date:
                try:
                    # Parse ISO format: 2026-06-15T10:00:00Z
                    dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    date_formatted = dt.strftime('%d/%m/%Y')
                    time_formatted = dt.strftime('%H:%M')
                except:
                    date_formatted = start_date.split('T')[0] if 'T' in start_date else start_date
                    time_formatted = '10:00'
            else:
                date_formatted = ''
                time_formatted = '10:00'
            
            # Extract customer info from search result
            customer = booking.get('customer', {})
            
            first_name = customer.get('firstName', '')
            last_name = customer.get('lastName', '')
            email = customer.get('email', '')
            phone = customer.get('phoneNumber', '')
            
            # Get total price to estimate visitors (search results don't have participant details)
            # We'll need to fetch full booking details for participant info
            total_price = booking.get('totalPrice', 0)
            
            # Estimate visitors from price (rough estimate - will be updated when we fetch full details)
            visitors = 1  # Default to 1, will be updated
            
            # For now, create one participant from customer info
            participants = [{
                'first_name': first_name,
                'last_name': last_name,
                'birth_date': '',
                'gender': 'M',
                'email': email,
                'phone': phone
            }]
            
            # Extract status
            status = booking.get('status', 'CONFIRMED')
            
            # Format for Google Sheets
            sheets_data = {
                'booking_id': booking_id,
                'date': date_formatted,
                'time': time_formatted,
                'visitors': visitors,
                'ticket_type': product_title,
                'customer': {
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'phone': phone
                },
                'participants': participants,
                'status': 'Pending',  # Always start as Pending for bot processing
                'created_at': booking.get('creationDate', datetime.now().isoformat()),
                'notes': f"Bokun Status: {status}"
            }
            
            logger.info(f"✅ Parsed booking {booking_id}: {date_formatted} at {time_formatted}, {visitors} visitors")
            return sheets_data
            
        except Exception as e:
            logger.error(f"Failed to parse booking: {e}")
            logger.error(f"Booking data: {booking}")
            return None
    
    def sync_bookings_to_sheets(self, from_date: datetime = None, to_date: datetime = None) -> int:
        """
        Fetch bookings from Bokun and sync to Google Sheets
        
        Args:
            from_date: Start date (defaults to today)
            to_date: End date (defaults to 90 days from now)
            
        Returns:
            Number of bookings synced
        """
        from backend.services.bokun_sheets_sync import get_bokun_sync
        
        # Fetch bookings from Bokun
        bookings = self.get_confirmed_bookings(from_date, to_date)
        
        if not bookings:
            logger.info("ℹ️ No bookings found in Bokun")
            return 0
        
        # Get Google Sheets sync service
        sheets_sync = get_bokun_sync()
        
        # Get existing bookings from Sheets to avoid duplicates
        existing_bookings = sheets_sync.get_pending_bookings()
        existing_ids = {b.get('Booking ID') for b in existing_bookings}
        
        synced_count = 0
        
        for booking in bookings:
            try:
                # Parse booking
                sheets_data = self.parse_booking_for_sheets(booking)
                
                if not sheets_data:
                    continue
                
                booking_id = sheets_data['booking_id']
                
                # Skip if already in Sheets
                if booking_id in existing_ids:
                    logger.info(f"⏭️ Skipping {booking_id} (already in Sheets)")
                    continue
                
                # Add to Google Sheets
                success = sheets_sync.add_booking_from_bokun(sheets_data)
                
                if success:
                    synced_count += 1
                    logger.info(f"✅ Synced booking {booking_id} to Google Sheets")
                
            except Exception as e:
                logger.error(f"Failed to sync booking: {e}")
                continue
        
        logger.info(f"✅ Synced {synced_count}/{len(bookings)} bookings to Google Sheets")
        return synced_count
    
    def test_connection(self) -> bool:
        """
        Test Bokun API connection
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to fetch bookings for a very narrow range (today)
            # This is a good test as it uses the same logic as real fetching
            from_date = datetime.now()
            to_date = datetime.now() + timedelta(days=1)
            
            # We don't use self.get_confirmed_bookings because it swallows exceptions
            from_str = from_date.strftime('%Y-%m-%dT00:00:00')
            to_str = to_date.strftime('%Y-%m-%dT23:59:59')
            
            query = {
                'startDateRange': {
                    'from': from_str,
                    'to': to_str,
                    'includeLower': True,
                    'includeUpper': True
                },
                'bookingStatuses': ['CONFIRMED'],
                'page': 0,
                'pageSize': 1
            }
            
            self._make_request(
                endpoint='/booking.json/booking-search',
                method='POST',
                data=query
            )
            
            logger.info("✅ Bokun API connection successful!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Bokun API connection failed: {e}")
            return False


# Singleton instance
_bokun_api = None

def get_bokun_api() -> BokunAPI:
    """Get or create BokunAPI instance"""
    global _bokun_api
    if _bokun_api is None:
        _bokun_api = BokunAPI()
    return _bokun_api


# Example usage
if __name__ == '__main__':
    # Test the Bokun API
    api = get_bokun_api()
    
    # Test connection
    print("Testing Bokun API connection...")
    if api.test_connection():
        print("✅ Connection successful!")
    else:
        print("❌ Connection failed!")
        exit(1)
    
    # Fetch bookings
    print("\nFetching bookings from Bokun...")
    bookings = api.get_confirmed_bookings()
    print(f"Found {len(bookings)} bookings")
    
    # Show first booking
    if bookings:
        print("\nFirst booking:")
        print(bookings[0])
        
        # Parse for Sheets
        print("\nParsed for Google Sheets:")
        sheets_data = api.parse_booking_for_sheets(bookings[0])
        print(sheets_data)
    
    # Sync to Sheets
    print("\nSyncing to Google Sheets...")
    synced = api.sync_bookings_to_sheets()
    print(f"✅ Synced {synced} bookings")
