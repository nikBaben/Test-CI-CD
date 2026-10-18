from src.modules.companies.application.events import CompanyCreated, CompanyUpdated
from src.modules.companies.infrastructure.broker.names import RoutingKeys


# Один реестр для записи outbox и восстановления события при отправке.
COMPANY_EVENT_ROUTES = {
    CompanyCreated.__name__: (CompanyCreated, RoutingKeys.COMPANY_CREATED),
    CompanyUpdated.__name__: (CompanyUpdated, RoutingKeys.COMPANY_UPDATED),
}
