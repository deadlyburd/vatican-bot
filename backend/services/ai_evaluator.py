import os
import logging
import json
from typing import Dict, Any, Tuple, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger(__name__)

class AIEvaluator:
    """
    AI Service to validate booking data for Vatican requirements.
    """
    
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.client = OpenAI(api_key=self.api_key) if (OpenAI and self.api_key) else None

    async def validate_task(self, task) -> Tuple[bool, str, List[str]]:
        """
        Validates a VaticanTask for completeness.
        Returns: (is_complete, summary_text, missing_fields_list)
        """
        if not self.client:
            logger.warning("AI Evaluator: OpenAI client not initialized. Falling back to rule-based validation.")
            return self._rule_based_validation(task)

        # Gather context for the AI
        participants = []
        if task.participants_data:
            participants = task.participants_data
        elif task.participants_json:
            try: participants = json.loads(task.participants_json)
            except: pass

        context = {
            "booking_id": task.booking_id,
            "visitors": task.visitors,
            "customer": {
                "name": task.customer_name,
                "email": task.customer_email,
                "phone": task.customer_phone
            },
            "participants": participants,
            "target_date": str(task.target_date),
            "target_time": task.target_time
        }

        prompt = f"""
Analyze the following Vatican ticket booking data and determine if it's complete enough to finalize a checkout on the official website.

Vatican Requirements:
1. Representative must have: First Name, Last Name, Email, Phone, Country, City, Birth Date.
2. Every participant (Total: {task.visitors}) must have: First Name, Last Name.
3. Birth dates are strongly recommended for all participants.

Data to analyze:
{json.dumps(context, indent=2)}

Respond ONLY with a JSON object in this format:
{{
  "is_complete": boolean,
  "summary": "Polite summary of findings",
  "missing_fields": ["field_name_1", "field_name_2"],
  "outreach_draft": "A short, polite message to the customer in English or Italian asking for the missing info."
}}
"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a data validation expert for a travel agency bot."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0
            )
            result = json.loads(response.choices[0].message.content)
            return result.get('is_complete', False), result.get('summary', ''), result.get('missing_fields', [])
        except Exception as e:
            logger.error(f"AI Evaluator failed: {e}")
            return self._rule_based_validation(task)

    def _rule_based_validation(self, task) -> Tuple[bool, str, List[str]]:
        """Fallback validation if AI fails or key is missing"""
        missing = []
        if not task.customer_name or len(task.customer_name.split()) < 2:
            missing.append("full_name")
        if not task.customer_email or '@' not in task.customer_email:
            missing.append("email")
        if not task.customer_phone:
            missing.append("phone")
            
        # Basic check for participants
        participants = []
        if task.participants_data:
            participants = task.participants_data
        elif task.participants_json:
            try: participants = json.loads(task.participants_json)
            except: pass
            
        if len(participants) < task.visitors:
            missing.append(f"participant_names_for_{task.visitors - len(participants)}_people")
            
        is_complete = len(missing) == 0
        summary = "Data is complete" if is_complete else f"Missing: {', '.join(missing)}"
        return is_complete, summary, missing

# Singleton
_evaluator = None
def get_evaluator():
    global _evaluator
    if _evaluator is None:
        _evaluator = AIEvaluator() # Internal name was different in my mental draft
    return _evaluator

class AIEvaluator(AIEvaluator): # Fix naming
    pass
