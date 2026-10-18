from dataclasses import dataclass

from src.shared.rabbitmq.contracts import EventPublisher


@dataclass(frozen=True)
class Publishers:
    """Готовые RabbitMQ publishers. Контейнер не создаёт и не закрывает ресурсы."""
    companies: EventPublisher
