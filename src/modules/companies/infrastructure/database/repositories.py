from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.companies.application.exceptions import CompanyAlreadyExistsError, CompanyStorageError, StoredCompanyNotFoundError
from src.modules.companies.domain.entities import Company
from src.modules.companies.infrastructure.database.mappers import to_entity, to_orm
from src.modules.companies.infrastructure.database.models import CompanyEconomicSectorORM, CompanyFinanceORM, CompanyORM
from src.modules.users.infrastructure.database.models import UserORM


class SQLAlchemyCompanyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def owner_exists(self, user_id: UUID) -> bool:
        try:
            return await self.session.scalar(select(UserORM.id).where(UserORM.id == user_id)) is not None
        except SQLAlchemyError as exc:
            raise CompanyStorageError() from exc

    async def _get(self, query) -> Company | None:
        try:
            row = await self.session.scalar(query)
            if row is None:
                return None
            financials = await self.session.scalar(
                select(CompanyFinanceORM).where(CompanyFinanceORM.company_id == row.id)
                .order_by(CompanyFinanceORM.year.desc()).limit(1).execution_options(populate_existing=True)
            )
            if financials is None:
                raise CompanyStorageError("У сохранённой компании нет отчётности")
            sectors = (await self.session.scalars(
                select(CompanyEconomicSectorORM).where(CompanyEconomicSectorORM.company_id == row.id)
                .order_by(CompanyEconomicSectorORM.position).execution_options(populate_existing=True)
            )).all()
            return to_entity(row, financials, sectors)
        except SQLAlchemyError as exc:
            raise CompanyStorageError() from exc

    async def get_by_id(self, user_id: UUID, company_id: UUID) -> Company | None:
        # Удерживаем согласованный снимок агрегата между чтением компании, финансов и ОКВЭД.
        query = select(CompanyORM).where(CompanyORM.id == company_id, CompanyORM.user_id == user_id).with_for_update(read=True)
        return await self._get(query)

    async def get_by_id_for_update(self, user_id: UUID, company_id: UUID) -> Company | None:
        query = select(CompanyORM).where(CompanyORM.id == company_id, CompanyORM.user_id == user_id).with_for_update().execution_options(populate_existing=True)
        return await self._get(query)

    async def get_by_inn(self, user_id: UUID, inn: int) -> Company | None:
        return await self._get(select(CompanyORM).where(CompanyORM.inn == inn, CompanyORM.user_id == user_id))

    async def add(self, company_id: UUID, user_id: UUID, company: Company) -> None:
        row, financials, sectors = to_orm(company_id, user_id, company)
        try:
            self.session.add(row)
            await self.session.flush()
            self.session.add(financials)
            self.session.add_all(sectors)
            await self.session.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise CompanyAlreadyExistsError() from exc
            raise CompanyStorageError() from exc
        except SQLAlchemyError as exc:
            raise CompanyStorageError() from exc

    async def update(self, company_id: UUID, user_id: UUID, company: Company) -> None:
        try:
            row = await self.session.scalar(
                select(CompanyORM).where(CompanyORM.id == company_id, CompanyORM.user_id == user_id)
                .with_for_update().execution_options(populate_existing=True)
            )
            if row is None:
                raise StoredCompanyNotFoundError()
            replacement, financials, sectors = to_orm(company_id, user_id, company)
            inn_changed = row.inn != company.inn
            for field in ("inn", "sales_model", "primary_sales_channel", "tax_regime", "key_vulnerability", "seasonality", "ceo_goal"):
                setattr(row, field, getattr(replacement, field))
            if inn_changed:
                for field in ("ogrn", "name", "full_name", "registered_at", "city", "employee_count",
                              "primary_okved_class", "primary_okved_name", "global_sector"):
                    setattr(row, field, getattr(replacement, field))
            await self.session.flush()
            if inn_changed:
                # Отчётность и ОКВЭД прежнего ИНН не должны принадлежать новой организации.
                await self.session.execute(delete(CompanyFinanceORM).where(CompanyFinanceORM.company_id == company_id))
                await self.session.execute(delete(CompanyEconomicSectorORM).where(CompanyEconomicSectorORM.company_id == company_id))
                self.session.add(financials)
                self.session.add_all(sectors)
                await self.session.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise CompanyAlreadyExistsError() from exc
            raise CompanyStorageError() from exc
        except SQLAlchemyError as exc:
            raise CompanyStorageError() from exc
