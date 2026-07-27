import os
import logging
import json
from datetime import datetime
from typing import List, Dict, Any

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger(__name__)

class AIAgent:
    """
    AI Agent that uses Google Sheets and Database as RAG source
    """
    
    def __init__(self):
        # Use DeepSeek API (OpenAI-compatible) — DEEPSEEK_API_KEY already configured
        self.api_key = os.getenv('DEEPSEEK_API_KEY') or os.getenv('OPENAI_API_KEY')
        if OpenAI and self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com/v1" if os.getenv('DEEPSEEK_API_KEY') else None
            )
        else:
            self.client = None
        
    def get_context(self) -> str:
        """
        Gathers data from Sheets and Database to build the context
        """
        from backend.services.bokun_sheets_sync import get_bokun_sync
        from monitors.models import MonitorTask, HeldSlot
        
        context = []
        context.append("--- SYSTEM STATUS ---")
        context.append(f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # 1. Sheets Data (Pending Bookings)
        try:
            sync = get_bokun_sync()
            pending = sync.get_pending_bookings()
            context.append("\n--- PENDING BOOKINGS (FROM SHEETS) ---")
            if not pending:
                context.append("No pending bookings in Google Sheets.")
            for b in pending[:10]: # Limit to 10 for context window
                context.append(f"- ID: {b.get('Booking ID')} | Date: {b.get('Date')} | Time: {b.get('Time')} | Visitors: {b.get('Visitors')} | Status: {b.get('Status')}")
        except Exception as e:
            logger.error(f"AI Context: Sheets fetch failed: {e}")
            
        # 2. Database Tasks
        try:
            tasks = MonitorTask.objects.filter(is_active=True).order_by('target_date')[:10]
            context.append("\n--- ACTIVE MONITORING TASKS (DATABASE) ---")
            if not tasks:
                context.append("No active monitoring tasks.")
            for t in tasks:
                context.append(f"- Task #{t.id} | {t.ticket_name} | Date: {t.target_date} | Time: {t.target_time} | Status: {t.status}")
        except Exception as e:
            logger.error(f"AI Context: DB fetch failed: {e}")

        # 3. Active Holds
        try:
            holds = HeldSlot.objects.filter(status='held')[:5]
            context.append("\n--- CURRENTLY HELD SLOTS ---")
            if not holds:
                context.append("No slots currently being held.")
            for h in holds:
                context.append(f"- Hold #{h.id} | {h.date} {h.slot_time} | {h.ticket_name} | Expiry: {h.hours_until_expiry()}h left")
        except Exception as e:
            logger.error(f"AI Context: Holds fetch failed: {e}")
            
        return "\n".join(context)

    async def answer_question(self, question: str) -> str:
        """
        Answers a user question using the gathered context
        """
        if not self.client:
            return "⚠️ API key not set. Add DEEPSEEK_API_KEY to your .env file."
            
        context = self.get_context()
        
        prompt = f"""
You are the Vatican Bot AI Assistant. You have access to real-time data from Google Sheets (Bokun bookings) and our internal monitoring database.
Use the context below to answer the user's question. If you don't know the answer, say you don't know.

{context}

User Question: {question}
Answer:
"""
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for a ticket booking bot system."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI Call failed: {e}")
            return f"❌ Sorry, I encountered an error while processing your question: {str(e)}"

# Singleton
_ai_agent = None
def get_ai_agent():
    global _ai_agent
    if _ai_agent is None:
        _ai_agent = AIAgent()
    return _ai_agent
