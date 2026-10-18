"""Companies owned by application users and their annual financial statements."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_create_companies"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("inn", sa.String(12), nullable=False),
        sa.Column("sales_model", sa.String(3), nullable=False),
        sa.Column("primary_sales_channel", sa.String(64), nullable=False),
        sa.Column("tax_regime", sa.String(16), nullable=False),
        sa.Column("key_vulnerability", sa.String(64), nullable=False),
        sa.Column("seasonality", sa.String(32), nullable=False),
        sa.Column("ceo_goal", sa.String(128), nullable=False),
        sa.Column("info", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "inn", name="uq_companies_user_inn"),
        sa.CheckConstraint("inn ~ '^([0-9]{10}|[0-9]{12})$'", name="ck_companies_inn"),
    )
    fields = (
        "revenue", "net_profit", "cost_of_sales", "gross_profit", "gross_profit_margin",
        "commercial_expenses", "administrative_expenses", "operating_expenses", "net_profit_margin",
        "operating_cash_flow", "current_ratio", "payroll_payments", "payroll_payment_share",
        "revenue_per_employee", "sales_expense_ratio", "cac", "ltv",
    )
    op.create_table(
        "companies_finance",
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        *(sa.Column(field, sa.Numeric(28, 2), nullable=True) for field in fields),
        sa.PrimaryKeyConstraint("company_id", "year"),
        sa.CheckConstraint("year >= 1900", name="ck_companies_finance_year"),
    )


def downgrade():
    op.drop_table("companies_finance")
    op.drop_table("companies")
