from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, DateTime, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.config import settings


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), index=True, default="queued")
    model_version: Mapped[str | None] = mapped_column(String(128))
    predicted_category: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)
    assigned_team: Mapped[str | None] = mapped_column(String(128))
    routing_snapshot: Mapped[dict | None] = mapped_column(JSON)
    routing_evidence: Mapped[dict | None] = mapped_column(JSON)
    threshold: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queue_wait_ms: Mapped[float | None] = mapped_column(Float)
    inference_ms: Mapped[float | None] = mapped_column(Float)
    last_error: Mapped[str | None] = mapped_column(String(128))


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), unique=True)
    category: Mapped[str] = mapped_column(String(64))
    team: Mapped[str] = mapped_column(String(128))
    reviewer: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


engine = create_engine(settings().database_url, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
