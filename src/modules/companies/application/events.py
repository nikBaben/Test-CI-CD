from uuid import UUID

from src.modules.companies.domain.entities import Company
from src.shared.rabbitmq.schemas import Event


class CompanyCreated(Event):
    """Полный снимок созданной компании, предназначенный другому сервису."""
    company_id: UUID
    user_id: UUID
    company: Company


class CompanyUpdated(Event):
    """Снимок компании после изменения бизнес-полей без смены ИНН."""
    company_id: UUID
    user_id: UUID
    company: Company


type CompanyEvent = CompanyCreated | CompanyUpdated
