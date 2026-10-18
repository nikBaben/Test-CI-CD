"""Преобразование доменных объектов в выходные DTO use case."""
from src.modules.companies.application.dto import CompanyDTO, CompanyInfoDTO, EconomicSectorDTO, FinancialInfoDTO
from src.modules.companies.domain.entities import Company, EconomicSectorCompany, FinancialInfoCompany, InfoCompany


def economic_sector_to_dto(sector: EconomicSectorCompany) -> EconomicSectorDTO:
    return EconomicSectorDTO(classOkved=sector.classOkved, name=sector.name, globalSector=sector.globalSector)


def company_info_to_dto(info: InfoCompany) -> CompanyInfoDTO:
    return CompanyInfoDTO(
        ogrn=info.ogrn, name=info.name, full_name=info.full_name, registered_at=info.registered_at,
        city=info.city, employee_count=info.employee_count,
        primaryEconomicSectorCompany=economic_sector_to_dto(info.primaryEconomicSectorCompany),
        economicSectorCompany=[economic_sector_to_dto(sector) for sector in info.economicSectorCompany],
    )


def financial_info_to_dto(financials: FinancialInfoCompany) -> FinancialInfoDTO:
    return FinancialInfoDTO(**financials.model_dump())


def company_to_dto(company: Company) -> CompanyDTO:
    return CompanyDTO(
        inn=company.inn, salesModel=company.salesModel, primarySalesChannel=company.primarySalesChannel,
        taxRegime=company.taxRegime, keyVulnerability=company.keyVulnerability, seasonality=company.seasonality,
        CEOGoal=company.CEOGoal, infoCompany=company_info_to_dto(company.infoCompany),
        financials=financial_info_to_dto(company.financials),
    )
