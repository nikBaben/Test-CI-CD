"""Move company information from JSONB into columns and ordered activity rows."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_normalize_company_info"
down_revision = "0003_company_inn_bigint"
branch_labels = None
depends_on = None

REQUIRED_FIELDS = {
    "ogrn": sa.Text(),
    "name": sa.Text(),
    "full_name": sa.Text(),
    "primary_okved_class": sa.Integer(),
    "primary_okved_name": sa.Text(),
}


def upgrade():
    for name, column_type in REQUIRED_FIELDS.items():
        op.add_column("companies", sa.Column(name, column_type, nullable=True))
    op.add_column("companies", sa.Column("registered_at", sa.Date(), nullable=True))
    op.add_column("companies", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("employee_count", sa.Integer(), nullable=True))
    op.create_table(
        "company_economic_sectors",
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("class_okved", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("company_id", "position"),
        sa.CheckConstraint("position >= 0", name="ck_company_economic_sectors_position"),
    )
    op.execute("""
        UPDATE companies SET
            ogrn = info ->> 'ogrn',
            name = info ->> 'name',
            full_name = info ->> 'full_name',
            registered_at = (info ->> 'registered_at')::date,
            city = info ->> 'city',
            employee_count = (info ->> 'employee_count')::integer,
            primary_okved_class = (info -> 'primaryEconomicSectorCompany' ->> 'classOkved')::integer,
            primary_okved_name = info -> 'primaryEconomicSectorCompany' ->> 'name'
    """)
    op.execute("""
        INSERT INTO company_economic_sectors (company_id, position, class_okved, name)
        SELECT c.id, (sector.ordinality - 1)::integer,
               (sector.value ->> 'classOkved')::integer, sector.value ->> 'name'
        FROM companies AS c
        CROSS JOIN LATERAL jsonb_array_elements(c.info -> 'economicSectorCompany')
            WITH ORDINALITY AS sector(value, ordinality)
    """)
    for name, column_type in REQUIRED_FIELDS.items():
        op.alter_column("companies", name, existing_type=column_type, nullable=False)
    op.drop_column("companies", "info")


def downgrade():
    op.add_column("companies", sa.Column("info", postgresql.JSONB(), nullable=True))
    op.execute("""
        UPDATE companies AS c SET info = jsonb_build_object(
            'ogrn', c.ogrn, 'name', c.name, 'full_name', c.full_name,
            'registered_at', c.registered_at, 'city', c.city, 'employee_count', c.employee_count,
            'primaryEconomicSectorCompany', jsonb_build_object(
                'classOkved', c.primary_okved_class, 'name', c.primary_okved_name
            ),
            'economicSectorCompany', COALESCE((
                SELECT jsonb_agg(jsonb_build_object('classOkved', s.class_okved, 'name', s.name) ORDER BY s.position)
                FROM company_economic_sectors AS s WHERE s.company_id = c.id
            ), '[]'::jsonb)
        )
    """)
    op.alter_column("companies", "info", existing_type=postgresql.JSONB(), nullable=False)
    op.drop_table("company_economic_sectors")
    for name in (*REQUIRED_FIELDS, "registered_at", "city", "employee_count"):
        op.drop_column("companies", name)
