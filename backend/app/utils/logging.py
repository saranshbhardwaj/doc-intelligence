# app/utils/logging.py
import logging
import os
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger
from app.config import settings

SERVICE_NAME = os.getenv("SERVICE_NAME", "backend")  # override in docker env if desired
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"

class ContextFilter(logging.Filter):
    def filter(self, record):
        # These may be injected via contextvars elsewhere; default to None if absent
        if not hasattr(record, "request_id"):
            record.request_id = None
        if not hasattr(record, "user_id"):
            record.user_id = None
        if not hasattr(record, "job_id"):
            record.job_id = None
        record.service = SERVICE_NAME
        return True

base_format = (
    "%(asctime)s %(levelname)s %(service)s %(name)s %(message)s "
    "%(exception)s %(request_id)s %(user_id)s %(job_id)s"
)

json_formatter = jsonlogger.JsonFormatter(
    base_format,
    rename_fields={"exception": "exception"}
)

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
logger.addFilter(ContextFilter())

# Console / stdout handler (always on for containers)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(json_formatter)
logger.addHandler(stream_handler)

# Optional file handler
if LOG_TO_FILE:
    file_handler = RotatingFileHandler(
        settings.log_dir / "app.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)

# Reduce noisy third-party loggers if needed
# Enable uvicorn.access for debugging, keep sqlalchemy quiet
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Convenience exported logger for modules still importing from here
application_logger = logger