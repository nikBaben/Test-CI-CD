"""PDF metadata; bytes live in a private MinIO bucket."""
from alembic import op
import sqlalchemy as sa

revision = "0006_company_documents"
down_revision = "0005_company_global_sector"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_companies_id_user", "companies", ["id", "user_id"])
    op.create_table(
        "company_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "user_id"], ["companies.id", "companies.user_id"],
                                ondelete="CASCADE", name="fk_company_documents_owned_company"),
        sa.UniqueConstraint("company_id", "document_type", "year", name="uq_company_documents_type_year"),
        sa.CheckConstraint("year BETWEEN 1900 AND 9999", name="ck_company_documents_year"),
        sa.CheckConstraint("size_bytes > 0", name="ck_company_documents_size"),
        sa.CheckConstraint("document_type IN ('balance_sheet', 'financial_results', 'changes_in_equity', 'cash_flows', 'targeted_funds')",
                           name="ck_company_documents_type"),
    )
    op.create_index("ix_company_documents_user_id", "company_documents", ["user_id"])


def downgrade():
    op.drop_index("ix_company_documents_user_id", table_name="company_documents")
    op.drop_table("company_documents")
    op.drop_constraint("uq_companies_id_user", "companies", type_="unique")
