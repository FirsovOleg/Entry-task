import threading
import time
from datetime import datetime

from .database import SessionLocal
from .services import process_intent
from .models import SendIntent
import logging

logger = logging.getLogger(__name__)


class Worker(threading.Thread):
    def __init__(self, stop_event):
        super().__init__(daemon=True)
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                intents = db.query(SendIntent).filter(
                    (SendIntent.next_attempt_at == None) | (SendIntent.next_attempt_at <= now)
                ).all()
                for intent in intents:
                    if self.stop_event.is_set():
                        break
                    try:
                        process_intent(db, intent)
                    except Exception:
                        db.rollback()
                        logger.exception("Error processing intent %s", getattr(intent, 'operation_id', None))
            except Exception:
                db.rollback()
                logger.exception("Worker loop error")
            finally:
                db.close()
            time.sleep(1)
