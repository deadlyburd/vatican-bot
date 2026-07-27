import logging
import time
from typing import List, Dict, Any
from worker_vatican.search_api_monitor import VaticanSearchAPIMonitor
from .models import Proxy

logger = logging.getLogger(__name__)

class DeepDiscoveryEngine:
    """
    Performs 'Deep Scans' by checking multiple visitor counts
    to find hidden inventory on the Vatican server.
    """
    
    def __init__(self, target_date: str, visitors_list: List[int] = [1, 2, 3, 4, 6, 8, 10]):
        self.target_date = target_date
        self.visitors_list = visitors_list
        # Fetch an active proxy
        self.proxy_obj = Proxy.objects.filter(is_active=True).order_by('?').first()
        proxy_str = None
        if self.proxy_obj:
            proxy_str = f"http://{self.proxy_obj.username}:{self.proxy_obj.password}@{self.proxy_obj.ip_port}"
        
        self.monitor = VaticanSearchAPIMonitor(proxy_str=proxy_str)

    def run(self) -> Dict[int, Any]:
        """Run the deep scan and return results keyed by visitor count."""
        results = {}
        logger.info(f"🚀 Starting Deep Scan for {self.target_date}...")
        
        for count in self.visitors_list:
            logger.info(f"🔍 Checking visitor count: {count}...")
            try:
                # Use resolve_ticket_ids to see what's available for this count
                tickets = self.monitor.resolve_ticket_ids(self.target_date, count)
                
                available = []
                for t in tickets:
                    avail = t.get('availability', 'SOLD_OUT')
                    if avail != 'SOLD_OUT':
                        # If potnetially available, get times
                        success, slots = self.monitor.check_availability(t['id'], self.target_date, count)
                        if success and slots:
                            available.append({
                                'name': t['name'],
                                'ticket_id': t['id'],
                                'availability': avail,
                                'slots': slots
                            })
                
                results[count] = available
                # Small sleep to be polite
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"❌ Error in Deep Scan for count {count}: {e}")
                results[count] = f"Error: {e}"
                
        return results

    def format_report(self, results: Dict[int, Any]) -> str:
        """Format the results into a friendly Telegram message."""
        lines = [f"🔎 *Deep Discovery Report* 🔍\n📅 Date: `{self.target_date}`\n"]
        
        found_anything = False
        for count, data in results.items():
            if isinstance(data, str):
                lines.append(f"👥 *{count} visitors*: ❌ {data}")
                continue
                
            if not data:
                # lines.append(f"👥 *{count} visitors*: 🔴 Sold Out")
                continue
            
            found_anything = True
            lines.append(f"👥 *{count} visitors*: ✅ *AVAILABLE*")
            for t in data:
                times = [s['time'] for s in t['slots']]
                times_str = ', '.join(times[:8])
                if len(times) > 8: times_str += "..."
                lines.append(f"  • {t['name']}")
                lines.append(f"    🕒 {times_str}")
            lines.append("")
            
        if not found_anything:
            lines.append("🔴 No inventory found for any visitor count.")
        
        return "\n".join(lines)
