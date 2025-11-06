# app/utils/logging.py
import logging
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger
from app.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File handler with rotation - includes exception info
file_handler = RotatingFileHandler(
    settings.log_dir / "app.log",
    maxBytes=10_000_000,
    backupCount=5,
    encoding="utf-8"
)
# Include exc_info (exception traceback) in JSON logs
file_formatter = jsonlogger.JsonFormatter(
    '%(asctime)s %(levelname)s %(name)s %(message)s %(exc_info)s %(request_id)s %(user_id)s %(job_id)s',
    rename_fields={"exc_info": "exception"}
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)