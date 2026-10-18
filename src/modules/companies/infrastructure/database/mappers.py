from uuid import UUID

from collections.abc import Sequence

from src.modules.companies.domain.entities import Company, EconomicSectorCompany, FinancialInfoCompany, InfoCompany
from src.modules.companies.infrastructure.database.models import CompanyEconomicSectorORM, CompanyFinanceORM, CompanyORM


def to_orm(company_id: UUID, user_id: UUID, company: Company) -> tuple[CompanyORM, CompanyFinanceORM, list[CompanyEconomicSectorORM]]:
    info = company.infoCompany
    row = CompanyORM(
        id=company_id, user_id=user_id, inn=company.inn, sales_model=company.salesModel.value,
        primary_sales_channel=company.primarySalesChannel.value, tax_regime=company.taxRegime.value,
        key_vulnerability=company.keyVulnerability.value, seasonality=company.seasonality.value,
        ceo_goal=company.CEOGoal.value,
        ogrn=info.ogrn, name=info.name, full_name=info.full_name,
        registered_at=info.registered_at, city=info.city, employee_count=info.employee_count,
        primary_okved_class=info.primaryEconomicSectorCompany.classOkved,
        primary_okved_name=info.primaryEconomicSectorCompany.name,
        global_sector=info.primaryEconomicSectorCompany.globalSector.value,
    )
    finance = CompanyFinanceORM(company_id=company_id, **company.financials.model_dump())
    sectors = [
        CompanyEconomicSectorORM(
            company_id=company_id, position=position, class_okved=sector.classOkved, name=sector.name,
            global_sector=sector.globalSector.value,
        )
        for position, sector in enumerate(info.economicSectorCompany)
    ]
    return row, finance, sectors


def to_entity(row: CompanyORM, finance: CompanyFinanceORM, sectors: Sequence[CompanyEconomicSectorORM]) -> Company:
    financials = FinancialInfoCompany(**{
        field: getattr(finance, field) for field in FinancialInfoCompany.model_fields
    })
    return Company.create(
        inn=row.inn, salesModel=row.sales_model, primarySalesChannel=row.primary_sales_channel,
        taxRegime=row.tax_regime, keyVulnerability=row.key_vulnerability, seasonality=row.seasonality,
        CEOGoal=row.ceo_goal,
        infoCompany=InfoCompany(
            ogrn=row.ogrn, name=row.name, full_name=row.full_name,
            registered_at=row.registered_at, city=row.city, employee_count=row.employee_count,
            primaryEconomicSectorCompany=EconomicSectorCompany(classOkved=row.primary_okved_class, name=row.primary_okved_name),
            economicSectorCompany=[EconomicSectorCompany(classOkved=sector.class_okved, name=sector.name) for sector in sectors],
        ),
        financials=financials,
    )
