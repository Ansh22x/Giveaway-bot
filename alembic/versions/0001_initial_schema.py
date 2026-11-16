"""Initial schema for Ultra Giveaway Bot

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. giveaways
    op.create_table(
        "giveaways",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("host_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default="Untitled Giveaway"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rules", sa.Text(), nullable=True),
        sa.Column("price_label", sa.Text(), nullable=True),
        sa.Column("draw_mode", sa.Text(), nullable=False, server_default="random"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("winner_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("draw_mode IN ('random', 'number')", name="ck_giveaways_draw_mode"),
        sa.CheckConstraint("status IN ('draft', 'open', 'locked', 'drawn', 'cancelled')", name="ck_giveaways_status"),
    )
    op.create_index("idx_giveaways_host_status", "giveaways", ["host_id", "status"])

    # 3. giveaway_media
    op.create_table(
        "giveaway_media",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("giveaway_id", sa.BigInteger(), sa.ForeignKey("giveaways.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('photo', 'video', 'document')", name="ck_giveaway_media_kind"),
    )

    # 4. giveaway_admins
    op.create_table(
        "giveaway_admins",
        sa.Column("giveaway_id", sa.BigInteger(), sa.ForeignKey("giveaways.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("added_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5. entries
    op.create_table(
        "entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("giveaway_id", sa.BigInteger(), sa.ForeignKey("giveaways.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("contact", sa.Text(), nullable=True),
        sa.Column("payment_note", sa.Text(), nullable=True),
        sa.Column("proof_file_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_payment"),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("resubmit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending_payment', 'awaiting_approval', 'approved', 'rejected')", name="ck_entries_status"),
        sa.CheckConstraint("number >= 1 AND number <= 100", name="ck_entries_number_range"),
        sa.UniqueConstraint("giveaway_id", "participant_id", name="uq_giveaway_participant"),
        sa.UniqueConstraint("giveaway_id", "number", name="uq_giveaway_number"),
    )
    op.create_index("idx_entries_giveaway_status", "entries", ["giveaway_id", "status"])
    op.create_index("idx_entries_participant", "entries", ["participant_id"])

    # 6. pending_actions
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("giveaway_id", sa.BigInteger(), nullable=True),
        sa.Column("entry_id", sa.BigInteger(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_pending_actions_telegram_id", "pending_actions", ["telegram_id"], unique=True)

    # 7. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("giveaway_id", sa.BigInteger(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 8. processed_updates
    op.create_table(
        "processed_updates",
        sa.Column("update_id", sa.BigInteger(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("processed_updates")
    op.drop_table("audit_log")
    op.drop_table("pending_actions")
    op.drop_table("entries")
    op.drop_table("giveaway_admins")
    op.drop_table("giveaway_media")
    op.drop_table("giveaways")
    op.drop_table("users")
