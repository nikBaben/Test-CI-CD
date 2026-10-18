"""Store company INN as an integer; domain owns INN validation."""
from alembic import op
import sqlalchemy as sa

revision = "0003_company_inn_bigint"
down_revision = "0002_create_companies"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_companies_inn", "companies", type_="check")
    op.alter_column(
        "companies", "inn", existing_type=sa.String(12), type_=sa.BigInteger(),
        existing_nullable=False, postgresql_using="inn::bigint",
    )


def downgrade():
    op.alter_column(
        "companies", "inn", existing_type=sa.BigInteger(), type_=sa.String(12),
        existing_nullable=False, postgresql_using="inn::varchar(12)",
    )
    op.create_check_constraint("ck_companies_inn", "companies", "inn ~ '^([0-9]{10}|[0-9]{12})$'")
