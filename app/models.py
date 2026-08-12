from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Status(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class Operation(Base):
    __tablename__ = "operations"
    id = Column(Integer, primary_key=True)
    operation_id = Column(String, unique=True, index=True, nullable=False)
    amount = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, nullable=False, default=Status.CREATED.value)
    provider_payment_id = Column(String, nullable=True, index=True)
    version = Column(Integer, default=0, nullable=False)

    events = relationship("Event", back_populates="operation", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    operation_id = Column(String, ForeignKey("operations.operation_id"), nullable=False)
    seq = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    message = Column(String, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow)

    operation = relationship("Operation", back_populates="events")

    __table_args__ = (UniqueConstraint("operation_id", "seq", name="uix_operation_seq"),)


class SendIntent(Base):
    __tablename__ = "send_intents"
    id = Column(Integer, primary_key=True)
    operation_id = Column(String, ForeignKey("operations.operation_id"), unique=True, nullable=False)
    attempts = Column(Integer, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
