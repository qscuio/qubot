import logging
import sys
import os
from app.core.config import settings

# Log file path for fail2ban integration
LOG_FILE = os.environ.get('LOG_FILE', '/var/log/qubot/app.log')

class Logger:
    _file_handler = None
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(settings.LOG_LEVEL.upper())
        
        # Prevent adding multiple handlers if already configured
        if not self.logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            # File handler (for fail2ban) - shared across all loggers
            if Logger._file_handler is None and os.path.isdir(os.path.dirname(LOG_FILE)):
                try:
                    Logger._file_handler = logging.FileHandler(LOG_FILE)
                    Logger._file_handler.setFormatter(formatter)
                except Exception:
                    pass  # Skip if can't write to file
            
            if Logger._file_handler:
                self.logger.addHandler(Logger._file_handler)

    def info(self, msg: str):
        self.logger.info(msg)

    def warn(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str, exc: Exception = None):
        self.logger.error(msg, exc_info=exc)

    def debug(self, msg: str):
        self.logger.debug(msg)

# Global configuration needed? 
# Usually logging.basicConfig is enough, but per-module loggers are better.

