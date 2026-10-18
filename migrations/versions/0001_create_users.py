"""Create application user profiles. Keycloak manages its own separate database."""
from alembic import op
import sqlalchemy as sa

revision = "0001_create_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("last_name", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column("patronymic", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(11), nullable=False),
        sa.Column("birthday", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_number", name="uq_users_phone_number"),
        sa.CheckConstraint("phone_number ~ '^79[0-9]{9}$'", name="ck_users_phone_number"),
    )


def downgrade():
    op.drop_table("users")
