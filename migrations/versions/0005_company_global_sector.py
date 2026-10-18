"""Persist the existing domain OKVED sector for primary and additional activities."""
from alembic import op
import sqlalchemy as sa

from src.modules.companies.domain.entities import EconomicSectorCompany

revision = "0005_company_global_sector"
down_revision = "0004_normalize_company_info"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("companies", sa.Column("global_sector", sa.Text(), nullable=True))
    op.add_column("company_economic_sectors", sa.Column("global_sector", sa.Text(), nullable=True))
    connection = op.get_bind()
    activities = connection.execute(sa.text("""
        SELECT primary_okved_class AS class_okved, primary_okved_name AS name FROM companies
        UNION
        SELECT class_okved, name FROM company_economic_sectors
    """)).mappings()
    sectors = {
        row["class_okved"]: EconomicSectorCompany(classOkved=row["class_okved"], name=row["name"]).globalSector.value
        for row in activities
    }
    companies = sa.table("companies", sa.column("primary_okved_class", sa.Integer()), sa.column("global_sector", sa.Text()))
    additional = sa.table("company_economic_sectors", sa.column("class_okved", sa.Integer()), sa.column("global_sector", sa.Text()))
    for class_okved, global_sector in sectors.items():
        connection.execute(companies.update().where(companies.c.primary_okved_class == class_okved).values(global_sector=global_sector))
        connection.execute(additional.update().where(additional.c.class_okved == class_okved).values(global_sector=global_sector))
    op.alter_column("companies", "global_sector", existing_type=sa.Text(), nullable=False)
    op.alter_column("company_economic_sectors", "global_sector", existing_type=sa.Text(), nullable=False)


def downgrade():
    op.drop_column("company_economic_sectors", "global_sector")
    op.drop_column("companies", "global_sector")
