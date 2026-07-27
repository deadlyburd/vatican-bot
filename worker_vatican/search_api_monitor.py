#!/usr/bin/env python3
"""
Vatican Search API Monitor - Simplified and Efficient
=====================================================
Uses Vatican's search API directly - no browser automation needed.
10x faster, more reliable, works for ALL days including Mondays.

Key Features:
- Direct API calls (no Playwright/browser)
- Works for all days (Monday-Sunday)
- Session management with JSESSIONID
- Automatic ticket ID resolution
- Fast and lightweight
"""

import logging
import requests
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class VaticanSearchAPIMonitor:
    """
    Simplified Vatican monitor using search API only.
    No browser automation required.
    """
    
    def __init__(self, proxy_str: Optional[str] = None):
        """Initialize the monitor. Uses proxy if provided, otherwise direct IP."""
        self.session = requests.Session()
        if proxy_str:
            self.session.proxies = {'http': proxy_str, 'https': proxy_str}
        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://tickets.museivaticani.va/',
            'Accept-Language': 'en-US,en;q=0.9,it;q=0.8',
            'Origin': 'https://tickets.museivaticani.va',
        }
    
    def normalize_date_format(self, date_str: str) -> str:
        """
        Normalize date to DD/MM/YYYY format (Vatican API format).
        
        Args:
            date_str: Date in DD/MM/YYYY or YYYY-MM-DD format
        
        Returns:
            Date in DD/MM/YYYY format
        """
        try:
            # If already in DD/MM/YYYY format, return as-is
            if '/' in date_str and len(date_str.split('/')[2]) == 4:
                return date_str
            
            # Convert from YYYY-MM-DD to DD/MM/YYYY
            if '-' in date_str:
                year, month, day = date_str.split('-')
                return f"{day}/{month}/{year}"
            
            # If format is unclear, try to parse and reformat
            return date_str
        except Exception as e:
            logger.warning(f"⚠️ Could not normalize date {date_str}: {e}")
            return date_str
    
    def get_vatican_timestamp(self, date_str: str) -> int:
        """
        Convert date string to Vatican timestamp (milliseconds since epoch in Rome timezone).
        
        Args:
            date_str: Date in DD/MM/YYYY or YYYY-MM-DD format
        
        Returns:
            Timestamp in milliseconds
        """
        try:
            if '/' in date_str:
                day, month, year = date_str.split('/')
            else:
                year, month, day = date_str.split('-')
            
            rome = ZoneInfo("Europe/Rome")
            dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
            timestamp_ms = int(dt.timestamp() * 1000)
            
            return timestamp_ms
        except Exception as e:
            logger.error(f"❌ Error converting date {date_str}: {e}")
            raise
    
    def resolve_ticket_ids(
        self,
        target_date: str,
        visitors: int,
        ticket_type: int = 0,
        language: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Resolve ticket IDs using search API.
        
        Args:
            target_date: Date in DD/MM/YYYY or YYYY-MM-DD format
            visitors: Number of visitors
            ticket_type: 0 for standard tickets, 1 for guided tours
            language: Language code (ENG, ITA, etc.) - for guided tours
        
        Returns:
            List of dicts with 'id', 'name', 'availability' keys
        
        Raises:
            requests.exceptions.Timeout: If rate limited or connection timeout
        """
        # Normalize date to DD/MM/YYYY format
        normalized_date = self.normalize_date_format(target_date)
        
        # Determine tag based on ticket type
        tag = 'MV-Biglietti' if ticket_type == 0 else 'MV-Visite-Guidate'
        
        url = "https://tickets.museivaticani.va/api/search/resultPerTag"
        params = {
            'lang': 'it',
            'visitorNum': str(visitors),
            'visitDate': normalized_date,
            'area': '1',
            'who': '',
            'page': '0',
            'tag': tag
        }
        
        logger.info(f"🔍 Resolving ticket IDs via search API...")
        logger.info(f"   Date: {normalized_date}, Visitors: {visitors}, Type: {'Standard' if ticket_type == 0 else 'Guided'}")
        
        try:
            response = self.session.get(
                url,
                params=params,
                headers=self.headers,
                timeout=8
            )
            
            # ✅ RATE LIMIT DETECTION
            if response.status_code == 429:
                logger.error(f"⚠️ RATE LIMITED (429) - Proxy needs rotation")
                raise requests.exceptions.Timeout("Rate limited (429)")
            
            if response.status_code == 503:
                logger.error(f"⚠️ Service unavailable (503) - Possible rate limit")
                raise requests.exceptions.Timeout("Service unavailable (503)")
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract JSESSIONID from cookies
                jsessionid = None
                for cookie in self.session.cookies:
                    if cookie.name == 'JSESSIONID':
                        jsessionid = cookie.value
                        break
                
                # Extract ticket information
                tickets = []
                for ticket in data.get('visits', []):
                    tickets.append({
                        'id': str(ticket['id']),
                        'name': ticket.get('name', 'Unknown'),
                        'availability': ticket.get('availability', 'UNKNOWN')
                    })
                
                logger.debug(f"Found {len(tickets)} tickets for {normalized_date}")
                return tickets
            else:
                logger.warning(f"Search API {response.status_code} for {normalized_date}")
                return []
                
        except requests.exceptions.Timeout as e:
            logger.warning(f"⚠️ Search API timeout {normalized_date}: {e}")
            raise  # Re-raise to trigger proxy rotation
        except Exception as e:
            logger.warning(f"Search API exception {normalized_date}: {e}")
            return []
    
    def match_ticket_by_name(
        self,
        tickets: List[Dict[str, str]],
        ticket_name: str,
        ticket_type: int = 0
    ) -> Optional[str]:
        """
        Match ticket by name using 3-tier strategy.
        
        Args:
            tickets: List of ticket dicts from search API
            ticket_name: Target ticket name to match
            ticket_type: 0 for standard, 1 for guided tours
        
        Returns:
            Ticket ID if found, None otherwise
        """
        if not tickets:
            return None
        
        ticket_name_lower = ticket_name.lower()
        
        # Strategy 1: Exact substring match
        for ticket in tickets:
            name = ticket.get('name', '').lower()
            if ticket_name_lower in name or name in ticket_name_lower:
                # Skip lunch tickets for standard tickets
                if ticket_type == 0 and any(x in name for x in ['lunch', 'pranzo']):
                    continue
                logger.info(f"✅ Exact match: {ticket['name']}")
                return ticket['id']
        
        # Strategy 2: Keyword scoring
        if ticket_type == 0:
            keywords = ['musei', 'vaticani', 'biglietti', 'ingresso', 'museum']
        else:
            keywords = ['visita', 'guidata', 'guided', 'tour']
        
        best_score = 0
        best_id = None
        best_name = None
        
        for ticket in tickets:
            name = ticket.get('name', '').lower()
            
            # Skip unwanted tickets
            if any(x in name for x in ['lunch', 'pranzo', 'pellegrinaggi', 'scuole']):
                continue
            
            score = sum(1 for kw in keywords if kw in name)
            if score > best_score:
                best_score = score
                best_id = ticket['id']
                best_name = ticket['name']
        
        if best_score >= 2:
            logger.info(f"✅ Keyword match (score {best_score}): {best_name}")
            return best_id
        
        # Strategy 3: Fallback to first standard ticket
        if ticket_type == 0:
            for ticket in tickets:
                name = ticket.get('name', '').lower()
                if 'musei vaticani' in name and 'biglietti' in name:
                    if not any(x in name for x in ['lunch', 'pranzo', 'gruppi', 'scuole']):
                        logger.info(f"✅ Fallback match: {ticket['name']}")
                        return ticket['id']
        else:
            # Guided tour fallback — pick first available guided tour ticket
            for ticket in tickets:
                name = ticket.get('name', '').lower()
                avail = ticket.get('availability', '')
                if avail not in ('SOLD_OUT', 'NOT_ALLOWED'):
                    if any(x in name for x in ['visita', 'guidat', 'guided', 'tour', 'singoli']):
                        logger.info(f"✅ Guided fallback match: {ticket['name']}")
                        return ticket['id']
        
        logger.warning(f"❌ No match found for: {ticket_name}")
        return None
    
    def check_availability(
        self,
        ticket_id: str,
        target_date: str,
        visitors: int,
        language: Optional[str] = None
    ) -> Tuple[bool, List[dict]]:
        """
        Check ticket availability using timeavail API.
        
        Args:
            ticket_id: Vatican ticket ID
            target_date: Date in DD/MM/YYYY or YYYY-MM-DD format
            visitors: Number of visitors
            language: Language code (empty for standard tickets)
        
        Returns:
            Tuple of (success: bool, available_slots: List[dict])
        """
        # Normalize date to DD/MM/YYYY format
        normalized_date = self.normalize_date_format(target_date)
        
        url = "https://tickets.museivaticani.va/api/visit/timeavail"
        
        # visitLang should be empty string for standard tickets
        visit_lang = language if language else ""
        
        params = {
            'lang': 'it',
            'visitLang': visit_lang,
            'visitTypeId': ticket_id,
            'visitorNum': str(visitors),
            'visitDate': normalized_date
        }
        
        logger.info(f"🔍 Checking availability...")
        logger.info(f"   Ticket ID: {ticket_id}")
        logger.info(f"   Date: {normalized_date}, Visitors: {visitors}")
        
        try:
            response = self.session.get(
                url,
                params=params,
                headers=self.headers,
                timeout=8
            )
            
            if response.status_code == 200:
                data = response.json()
                timetable = data.get('timetable', [])
                available_slots = [
                    {'id': s.get('id'), 'time': s.get('time'),
                     'availability': s.get('availability')}
                    for s in timetable
                    if s.get('availability') == 'AVAILABLE'
                    and (s.get('residual') is None or s.get('residual', 0) > 0)
                ]
                logger.debug(f"Timeavail: {len(available_slots)}/{len(timetable)} available")
                return True, available_slots
            elif response.status_code == 500:
                return True, []
            else:
                return True, []
                
        except Exception as e:
            logger.warning(f"Timeavail exception: {e}")
            return True, []
    
    def check_ticket(
        self,
        target_date: str,
        ticket_name: str,
        visitors: int,
        ticket_type: int = 0,
        language: Optional[str] = None
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Complete check: resolve ticket ID and check availability.
        
        Args:
            target_date: Date in DD/MM/YYYY format
            ticket_name: Ticket name to search for
            visitors: Number of visitors
            ticket_type: 0 for standard, 1 for guided tours
            language: Language code (for guided tours)
        
        Returns:
            Tuple of (success: bool, available_slots: List[str], ticket_id: Optional[str])
        """
        logger.info(f"🎫 Starting ticket check...")
        logger.info(f"   Date: {target_date}")
        logger.info(f"   Ticket: {ticket_name}")
        logger.info(f"   Visitors: {visitors}")
        
        # Step 1: Resolve ticket IDs
        tickets = self.resolve_ticket_ids(target_date, visitors, ticket_type, language)
        
        if not tickets:
            logger.warning(f"⚠️ No tickets returned from search API for {target_date} - treating as sold_out")
            return True, [], None  # Return success=True, empty slots = sold_out (not error)
        
        # Step 2: Match ticket by name
        ticket_id = self.match_ticket_by_name(tickets, ticket_name, ticket_type)
        
        if not ticket_id:
            logger.warning(f"⚠️ Could not match ticket '{ticket_name}' - treating as sold_out")
            return True, [], None  # Return success=True, empty slots = sold_out (not error)

        # ✅ OPTIMIZATION: If search API already says SOLD_OUT, skip timeavail entirely
        # Vatican returns HTTP 500 on timeavail for sold-out tickets - no point calling it
        matched_ticket = next((t for t in tickets if t['id'] == ticket_id), None)
        if matched_ticket and matched_ticket.get('availability') in ('SOLD_OUT', 'NOT_ALLOWED'):
            logger.info(f"⏭️ Search API says {matched_ticket['availability']} for {ticket_name} - skipping timeavail")
            return True, [], ticket_id  # sold_out, no error
        
        # Step 3: Check availability
        success, available_slots = self.check_availability(
            ticket_id, target_date, visitors, language
        )
        
        if not success:
            logger.warning(f"⚠️ Timeavail API failed for {ticket_id} - treating as sold_out")
            return True, [], ticket_id  # Return success=True, empty slots = sold_out (not error)
        
        return True, available_slots, ticket_id


# Convenience function for backward compatibility
def check_vatican_availability(
    target_date: str,
    ticket_name: str,
    visitors: int,
    ticket_type: int = 0,
    language: Optional[str] = None,
    proxy_str: Optional[str] = None
) -> Tuple[bool, List[str], Optional[str]]:
    """
    Convenience function to check Vatican ticket availability.
    
    Returns:
        Tuple of (success: bool, available_slots: List[str], ticket_id: Optional[str])
    """
    monitor = VaticanSearchAPIMonitor(proxy_str=proxy_str)
    return monitor.check_ticket(target_date, ticket_name, visitors, ticket_type, language)
