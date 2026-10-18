from src.shared.rabbitmq.names import ExchangeName, QueueName, RoutingKey


class Exchanges(ExchangeName):
    COMPANIES = "account-service.companies"
    FAILED = "account-service.failed"


class Queues(QueueName):
    COMPANY_CREATED = "account-service.company-created"
    COMPANY_UPDATED = "account-service.company-updated"
    FAILED = "account-service.failed"


class RoutingKeys(RoutingKey):
    COMPANY_CREATED = "company.created"
    COMPANY_UPDATED = "company.updated"
    ALL_FAILED = "#"
