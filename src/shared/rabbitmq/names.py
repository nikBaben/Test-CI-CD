"""Базовые типы имён. Разрешённые значения задаёт проект-пользователь."""

from enum import StrEnum


class ExchangeName(StrEnum):
    """Имя exchange. Для default exchange можно объявить значение пустой строки."""


class QueueName(StrEnum):
    """Имя очереди."""


class RoutingKey(StrEnum):
    """Ключ маршрутизации или шаблон привязки, например order.*."""
