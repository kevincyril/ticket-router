"""Ticket state and separate curated-feedback candidates."""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None


def upgrade():
    op.create_table("tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), unique=True, nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("model_version", sa.String(128)),
        sa.Column("predicted_category", sa.String(64)),
        sa.Column("confidence", sa.Float()),
        sa.Column("assigned_team", sa.String(128)),
        sa.Column("routing_snapshot", sa.JSON()),
        sa.Column("threshold", sa.Float()),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("dispatch_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("queue_wait_ms", sa.Float()),
        sa.Column("inference_ms", sa.Float()),
        sa.Column("last_error", sa.String(128)))
    for name in ("status", "dispatch_after", "created_at"):
        op.create_index(f"ix_tickets_{name}", "tickets", [name])
    op.create_table("reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id"), unique=True, nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("team", sa.String(128), nullable=False),
        sa.Column("reviewer", sa.String(80), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("reviews")
    op.drop_table("tickets")
