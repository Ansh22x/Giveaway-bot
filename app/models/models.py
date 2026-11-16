from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    CheckConstraint,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base

JSONType = JSON().with_variant(JSONB, "postgresql")
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(Text, nullable=True)
    first_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    entries = relationship("Entry", back_populates="participant", foreign_keys="Entry.participant_id")
    hosted_giveaways = relationship("Giveaway", back_populates="host", foreign_keys="Giveaway.host_id")


class Giveaway(Base):
    __tablename__ = "giveaways"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    host_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    title = Column(Text, nullable=False, default="Untitled Giveaway")
    description = Column(Text, nullable=True)
    rules = Column(Text, nullable=True)
    price_label = Column(Text, nullable=True)
    draw_mode = Column(
        Text,
        CheckConstraint("draw_mode IN ('random', 'number')"),
        default="random",
        nullable=False,
    )
    status = Column(
        Text,
        CheckConstraint("status IN ('draft', 'open', 'locked', 'drawn', 'cancelled')"),
        default="draft",
        nullable=False,
    )
    winner_entry_id = Column(BigInteger, nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    host = relationship("User", back_populates="hosted_giveaways", foreign_keys=[host_id])
    media = relationship("GiveawayMedia", back_populates="giveaway", cascade="all, delete-orphan", order_by="GiveawayMedia.sort_order")
    admins = relationship("GiveawayAdmin", back_populates="giveaway", cascade="all, delete-orphan")
    entries = relationship("Entry", back_populates="giveaway", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_giveaways_host_status", "host_id", "status"),
    )


class GiveawayMedia(Base):
    __tablename__ = "giveaway_media"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    giveaway_id = Column(BigInteger, ForeignKey("giveaways.id", ondelete="CASCADE"), nullable=False)
    kind = Column(
        Text,
        CheckConstraint("kind IN ('photo', 'video', 'document')"),
        nullable=False,
    )
    file_id = Column(Text, nullable=False)
    caption = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    giveaway = relationship("Giveaway", back_populates="media")


class GiveawayAdmin(Base):
    __tablename__ = "giveaway_admins"

    giveaway_id = Column(BigInteger, ForeignKey("giveaways.id", ondelete="CASCADE"), primary_key=True)
    telegram_id = Column(BigInteger, primary_key=True)
    added_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    giveaway = relationship("Giveaway", back_populates="admins")


class Entry(Base):
    __tablename__ = "entries"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    giveaway_id = Column(BigInteger, ForeignKey("giveaways.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    full_name = Column(Text, nullable=False)
    contact = Column(Text, nullable=True)
    payment_note = Column(Text, nullable=True)
    proof_file_id = Column(Text, nullable=True)
    status = Column(
        Text,
        CheckConstraint("status IN ('pending_payment', 'awaiting_approval', 'approved', 'rejected')"),
        default="pending_payment",
        nullable=False,
    )
    number = Column(
        Integer,
        CheckConstraint("number >= 1 AND number <= 100"),
        nullable=True,
    )
    approved_by = Column(BigInteger, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    reject_reason = Column(Text, nullable=True)
    resubmit_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    giveaway = relationship("Giveaway", back_populates="entries")
    participant = relationship("User", back_populates="entries", foreign_keys=[participant_id])

    __table_args__ = (
        UniqueConstraint("giveaway_id", "participant_id", name="uq_giveaway_participant"),
        UniqueConstraint("giveaway_id", "number", name="uq_giveaway_number"),
        Index("idx_entries_giveaway_status", "giveaway_id", "status"),
        Index("idx_entries_participant", "participant_id"),
    )


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    giveaway_id = Column(BigInteger, nullable=True)
    entry_id = Column(BigInteger, nullable=True)
    state = Column(Text, nullable=False)
    payload = Column(JSONType, nullable=True, default=dict)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_pending_actions_telegram_id", "telegram_id", unique=True),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    actor_id = Column(BigInteger, nullable=False)
    action = Column(Text, nullable=False)
    giveaway_id = Column(BigInteger, nullable=True)
    meta = Column(JSONType, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"

    update_id = Column(BigInteger, primary_key=True)
    processed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
