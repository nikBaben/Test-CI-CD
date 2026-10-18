"""Сохраняет типы AMQP options в JSON, включая bytes, Decimal и время."""
from base64 import b64decode, b64encode
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from src.shared.rabbitmq.names import QueueName


def encode(value: Any) -> Any:
    if isinstance(value, QueueName):
        return {"type": "queue", "value": value.value}
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"type": "timedelta", "value": value.total_seconds()}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"type": "bytes", "value": b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {"type": "dict", "value": {key: encode(item) for key, item in value.items()}}
    if isinstance(value, (list, tuple)):
        return {"type": "list", "value": [encode(item) for item in value]}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Неподдерживаемый тип параметра публикации: {type(value).__name__}")


def decode(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    kind, item = value["type"], value["value"]
    if kind == "queue":
        return QueueName("OutboxReplyQueue", {"VALUE": item}).VALUE
    if kind == "datetime":
        return datetime.fromisoformat(item)
    if kind == "timedelta":
        return timedelta(seconds=item)
    if kind == "decimal":
        return Decimal(item)
    if kind == "bytes":
        return b64decode(item)
    if kind == "dict":
        return {key: decode(child) for key, child in item.items()}
    if kind == "list":
        return [decode(child) for child in item]
    raise ValueError("Неизвестный тип параметра публикации в outbox")
