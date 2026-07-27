"""
AI Agents for Vatican Ticket Monitoring & Sniping
==================================================

Specialized agents for continuous monitoring and on-demand ticket acquisition.
"""

import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AIAgentBase:
    """Base class for all AI agents"""
    
    def __init__(self, agent_name):
        self.agent_name = agent_name
        self.last_run = None
        self.failures = 0
        self.max_failures = int(os.getenv('MAX_FAILURES', 3))
    
    def log_start(self):
        """Log agent startup"""
        logger.info(f"🤖 {self.agent_name} starting...")
        self.last_run = datetime.now()
    
    def log_success(self):
        """Log successful run"""
        logger.info(f"✅ {self.agent_name} completed successfully")
        self.failures = 0
    
    def log_failure(self, error):
        """Log failure and check if agent should be restarted"""
        self.failures += 1
        logger.error(f"❌ {self.agent_name} failed (attempt {self.failures}/{self.max_failures}): {error}")
        
        if self.failures >= self.max_failures:
            logger.critical(f"🚨 {self.agent_name} reached max failures - needs manual intervention")
            return False
        return True
    
    def should_run(self):
        """Check if agent should run based on schedule"""
        return True  # Override in subclasses
    
    def run(self):
        """Main execution method to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement run()")