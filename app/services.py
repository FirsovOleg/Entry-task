from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx
import logging
from sqlalchemy import update
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from .database import SessionLocal, engine
from .models import Operation, Event, SendIntent, Status, Base
from .config import settings

logger = logging.getLogger(__name__)


def init_db():
    Base.metadata.create_all(bind=engine)


def create_operation(db, operation_id: str, amount: str, currency: str, description: Optional[str]):
    # validate amount
    try:
        a = Decimal(amount)
        if a <= 0:
            raise ValueError("amount must be positive")
    except (InvalidOperation, ValueError):
        raise ValueError("invalid amount")

    op = Operation(
        operation_id=operation_id,
        amount=f"{a:.2f}",
        currency=currency,
        description=description,
        status=Status.CREATED.value,
    )
    db.add(op)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise

    # create event seq
    seq = 1
    ev = Event(
        operation_id=operation_id,
        seq=seq,
        type=Status.CREATED.value,
        from_status=None,
        to_status=Status.CREATED.value,
        message="Operation created",
        occurred_at=datetime.utcnow(),
    )
    db.add(ev)
    db.commit()
    db.refresh(op)
    return op


def get_operation(db, operation_id: str):
    return db.execute(select(Operation).where(Operation.operation_id == operation_id)).scalar_one_or_none()


def get_events(db, operation_id: str):
    return db.execute(select(Event).where(Event.operation_id == operation_id).order_by(Event.seq)).scalars().all()


def submit_operation(db, operation_id: str):
    # must atomically check CREATED and create SendIntent and move to PROCESSING
    op = get_operation(db, operation_id)
    if not op:
        return None

    if op.status != Status.CREATED.value:
        return op

    # create intent and update status inside transaction
    try:
        intent = SendIntent(operation_id=operation_id, attempts=0, next_attempt_at=datetime.utcnow())
        db.add(intent)
        # update operation status
        from_status = op.status
        op.status = Status.PROCESSING.value
        # add event with seq = max+1
        row = db.execute(select(func.max(Event.seq)).where(Event.operation_id == operation_id)).scalar()
        seq = (row or 0) + 1
        ev = Event(
            operation_id=operation_id,
            seq=seq,
            type=Status.PROCESSING.value,
            from_status=from_status,
            to_status=Status.PROCESSING.value,
            message="Submit requested",
            occurred_at=datetime.utcnow(),
        )
        db.add(ev)
        db.commit()
    except IntegrityError:
        db.rollback()
        # concurrent submit created intent first — return current state
        op = get_operation(db, operation_id)
    return op


# We intentionally do not record a separate SENT event to avoid reordering issues.
# Provider acceptance is persisted by setting `provider_payment_id` atomically with intent removal.


def handle_receipt(db, provider_payment_id: str, operation_id: str, result: str, message: str, occurred_at: str):
    # Optimistic concurrency with version field to avoid races between concurrent receipts
    for attempt in range(3):
        op = get_operation(db, operation_id)
        if not op:
            return None, 404

        # conflict if provider id present and differs
        if op.provider_payment_id and op.provider_payment_id != provider_payment_id:
            return None, 409

        # if already final with same provider and same result -> idempotent
        if op.provider_payment_id == provider_payment_id and op.status == result:
            return op, 204

        # if already final but different result -> record ignored and return 204
        if op.status in (Status.COMPLETED.value, Status.REJECTED.value):
            # record ignored
            row = db.execute(select(func.max(Event.seq)).where(Event.operation_id == operation_id)).scalar()
            seq = (row or 0) + 1
            ev = Event(
                operation_id=operation_id,
                seq=seq,
                type="RECEIPT_IGNORED",
                from_status=op.status,
                to_status=op.status,
                message=f"Ignored receipt {result}: {message}",
                occurred_at=datetime.utcnow(),
            )
            db.add(ev)
            db.commit()
            return op, 204

        # attempt to update with version check
        old_version = op.version
        stmt = (
            update(Operation)
            .where(
                Operation.operation_id == operation_id,
                Operation.version == old_version,
            )
            .values(
                status=result,
                provider_payment_id=provider_payment_id,
                version=old_version + 1,
            )
        )
        res = db.execute(stmt)
        if res.rowcount == 1:
            # success -> append event
            row = db.execute(select(func.max(Event.seq)).where(Event.operation_id == operation_id)).scalar()
            seq = (row or 0) + 1
            ev = Event(
                operation_id=operation_id,
                seq=seq,
                type=result,
                from_status=op.status,
                to_status=result,
                message=message,
                occurred_at=datetime.utcnow(),
            )
            db.add(ev)
            db.commit()
            return get_operation(db, operation_id), 204

        # someone else modified, retry
        db.rollback()
    # After retries, re-read and decide
    op = get_operation(db, operation_id)
    if not op:
        return None, 404
    if op.provider_payment_id == provider_payment_id and op.status == result:
        return op, 204
    # otherwise consider it conflict/ignored
    return None, 409


def process_intent(db, intent: SendIntent):
    # call provider
    operation = get_operation(db, intent.operation_id)
    if not operation:
        # remove intent
        db.delete(intent)
        db.commit()
        return

    payload = {"operationId": operation.operation_id, "amount": operation.amount, "currency": operation.currency}
    headers = {"Idempotency-Key": operation.operation_id, "X-Correlation-ID": operation.operation_id}
    try:
        r = httpx.post(f"{settings.PROVIDER_URL}/payments", json=payload, headers=headers, timeout=5.0)
    except Exception as exc:
        logger.warning("Network error calling provider for %s: %s", operation.operation_id, exc)
        # network error: schedule retry
        intent.attempts += 1
        intent.next_attempt_at = datetime.utcnow() + timedelta(seconds=settings.RETRY_BACKOFF_SECONDS)
        db.add(intent)
        db.commit()
        return

    # Treat 202 as success, 5xx as retryable, others as terminal (no retry)
    if r.status_code == 202:
        try:
            data = r.json()
        except Exception:
            data = {}
        provider_payment_id = data.get("providerPaymentId")
        # persist provider_payment_id and remove intent in one transaction
        try:
            op2 = db.query(Operation).filter(Operation.operation_id == operation.operation_id).one_or_none()
            if op2:
                if not op2.provider_payment_id and provider_payment_id:
                    op2.provider_payment_id = provider_payment_id
                    op2.version = (op2.version or 0) + 1
                # do not change status here; final state only via receipt
            db.delete(intent)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to persist provider response for %s: %s", operation.operation_id, exc)
        return
    elif 500 <= r.status_code:
        # server errors -> retry
        intent.attempts += 1
        intent.next_attempt_at = datetime.utcnow() + timedelta(seconds=settings.RETRY_BACKOFF_SECONDS)
        db.add(intent)
        db.commit()
        return
    else:
        # client errors (4xx) -> give up and remove intent
        db.delete(intent)
        db.commit()
        return
