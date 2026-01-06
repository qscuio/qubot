import logging
import sys
from app.core.config import settings

class Logger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(settings.LOG_LEVEL.upper())
        
        # Prevent adding multiple handlers if already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

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
