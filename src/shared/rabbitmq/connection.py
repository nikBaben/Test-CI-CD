import asyncio
from ssl import SSLContext
from typing import Literal, Self

import aio_pika
from aio_pika.abc import (
    AbstractRobustChannel,
    AbstractRobustConnection,
    HeadersType,
)

from src.shared.config import RabbitMQSettings


class RabbitMQConnection:
    """Соединение с восстановлением после обрыва и созданием каналов."""

    def __init__(
        self,
        settings: RabbitMQSettings | None = None,
        *,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        login: str | None = None,
        password: str | None = None,
        virtualhost: str | None = None,
        ssl: bool | None = None,
        heartbeat: int | None = None,
        reconnect_interval: float | None = None,
        connect_timeout: float | None = None,
        fail_fast: bool | None = None,
        name: str | None = None,
        auth: Literal["plain", "external"] | None = None,
        interleave: int | None = None,
        happy_eyeballs_delay: float | None = None,
        ssl_context: SSLContext | None = None,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | None = None,
        certfile: str | None = None,
        keyfile: str | None = None,
        no_verify_ssl: bool | None = None,
        client_properties: HeadersType | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        connection_class: type[AbstractRobustConnection] = aio_pika.RobustConnection,
    ) -> None:
        """Подготовить настройки. Само соединение открывается в connect().

        Явные аргументы заменяют соответствующие поля settings.
        None оставляет значение из settings. Переданные host/port/login/
        password/virtualhost/ssl включают раздельные настройки адреса, если URL
        не передан явно. Для отключения таймаута задайте его в settings как None.
        cadata принимает сертификат CA в кодировке base64, как ожидает aiormq.
        """
        if settings is None:
            settings = RabbitMQSettings()

        # Копия позволяет переопределять поля, не меняя переданный объект.
        self._settings = settings.model_copy()

        # Явный URL имеет приоритет. Раздельный адрес отключает URL из settings.
        if url is not None:
            self._settings.url = url
        elif any(
            value is not None
            for value in (host, port, login, password, virtualhost, ssl)
        ):
            self._settings.url = None
        if host is not None:
            self._settings.host = host
        if port is not None:
            self._settings.port = port
        if login is not None:
            self._settings.login = login
        if password is not None:
            self._settings.password = password
        if virtualhost is not None:
            self._settings.virtualhost = virtualhost
        if ssl is not None:
            self._settings.ssl = ssl
        if heartbeat is not None:
            self._settings.heartbeat = heartbeat
        if reconnect_interval is not None:
            self._settings.reconnect_interval = reconnect_interval
        if connect_timeout is not None:
            self._settings.connect_timeout = connect_timeout
        if fail_fast is not None:
            self._settings.fail_fast = fail_fast

        self._name = name
        self._auth = auth
        self._interleave = interleave
        self._happy_eyeballs_delay = happy_eyeballs_delay
        self._ssl_context = ssl_context
        self._cafile = cafile
        self._capath = capath
        self._cadata = cadata
        self._certfile = certfile
        self._keyfile = keyfile
        self._no_verify_ssl = no_verify_ssl
        self._client_properties = client_properties
        self._loop = loop
        self._connection_class = connection_class

        self._connection: AbstractRobustConnection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Открыть соединение. Повторный вызов использует уже открытое."""
        # Два одновременных вызова не должны открыть два соединения.
        async with self._lock:
            if self._connection is not None and not self._connection.is_closed:
                return

            self._connection = await aio_pika.connect_robust(
                self._settings.url,
                host=self._settings.host,
                port=self._settings.port,
                login=self._settings.login,
                password=self._settings.password,
                virtualhost=self._settings.virtualhost,
                ssl=self._settings.ssl,
                heartbeat=self._settings.heartbeat,
                reconnect_interval=self._settings.reconnect_interval,
                timeout=self._settings.connect_timeout,
                fail_fast=self._settings.fail_fast,
                name=self._name,
                auth=self._auth,
                interleave=self._interleave,
                happy_eyeballs_delay=self._happy_eyeballs_delay,
                ssl_context=self._ssl_context,
                cafile=self._cafile,
                capath=self._capath,
                cadata=self._cadata,
                certfile=self._certfile,
                keyfile=self._keyfile,
                no_verify_ssl=self._no_verify_ssl,
                client_properties=self._client_properties,
                loop=self._loop,
                connection_class=self._connection_class,
            )

    async def create_channel(
        self,
        *,
        publisher_confirms: bool = True,
        on_return_raises: bool = False,
        channel_number: int | None = None,
    ) -> AbstractRobustChannel:
        """Создать канал с выбранным режимом подтверждения публикаций."""
        async with self._lock:
            connection = self._connection

            if connection is None or connection.is_closed:
                raise RuntimeError("Соединение с RabbitMQ не установлено")

            channel = await connection.channel(
                channel_number=channel_number,
                publisher_confirms=publisher_confirms,
                on_return_raises=on_return_raises,
            )

            await channel.ready()
            return channel

    async def close(self) -> None:
        """Закрыть соединение и освободить ссылку на него."""
        async with self._lock:
            if self._connection is None:
                return

            try:
                await self._connection.close()
            finally:
                self._connection = None

    async def __aenter__(self) -> Self:
        """Открыть соединение при входе в async with."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        """Закрыть соединение при выходе из async with, в том числе при ошибке."""
        await self.close()
