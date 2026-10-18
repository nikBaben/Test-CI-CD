import asyncio
import logging
from collections.abc import Awaitable, Callable

from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractRobustChannel,
    AbstractRobustQueue,
    HeadersType,
)

from src.shared.rabbitmq.schemas import Event

logger = logging.getLogger(__name__)

type EventHandler[EventT: Event] = Callable[[EventT], Awaitable[None]]
type MessageHandler[EventT: Event] = Callable[
    [EventT, AbstractIncomingMessage], Awaitable[None]
]


class RabbitMQConsumer[EventT: Event]:
    """Чтение событий из очереди и управление подтверждением обработки."""

    def __init__(
        self,
        channel: AbstractRobustChannel,
        queue: AbstractRobustQueue,
        event_type: type[EventT],
        handler: EventHandler[EventT] | None = None,
        *,
        message_handler: MessageHandler[EventT] | None = None,
        auto_ack: bool = True,
        requeue_on_error: bool = False,
        requeue_on_invalid: bool = False,
    ) -> None:
        """Выбрать один обработчик: handler или message_handler.

        handler получает событие. message_handler дополнительно получает
        исходное сообщение: его заголовки, ack и reject.
        При auto_ack=False подтверждением валидных сообщений управляет обработчик.
        Ошибки формата сообщения всегда обрабатывает библиотека.
        """
        if handler is None and message_handler is None:
            raise ValueError("Укажите handler или message_handler")
        if handler is not None and message_handler is not None:
            raise ValueError("Нельзя одновременно указать handler и message_handler")
        if not auto_ack and message_handler is None:
            raise ValueError("Для ручного подтверждения нужен message_handler")

        self._channel = channel
        self._queue = queue
        self._event_type = event_type
        self._handler = handler
        self._message_handler = message_handler
        self._auto_ack = auto_ack
        self._requeue_on_error = requeue_on_error
        self._requeue_on_invalid = requeue_on_invalid
        self._no_ack = False
        self._lifecycle_lock = asyncio.Lock()

        self._consumer_tag: str | None = None
        self._active_tasks: set[asyncio.Task[None]] = set()

    async def start(
        self,
        *,
        prefetch_count: int = 10,
        prefetch_size: int = 0,
        global_: bool = False,
        qos_timeout: float | None = None,
        no_ack: bool = False,
        exclusive: bool = False,
        arguments: HeadersType | None = None,
        priority: int | None = None,
        consumer_tag: str | None = None,
        timeout: float | None = None,
        robust: bool = True,
    ) -> None:
        """Начать получать сообщения с заданными ограничениями и параметрами.

        prefetch_count — максимум неподтверждённых сообщений, 0 снимает лимит.
        no_ack=True отключает ожидание подтверждений со стороны брокера:
        библиотека не вызывает ack/reject, даже если обработчик завершился ошибкой.
        robust=True восстанавливает подписку при переподключении.
        """
        async with self._lifecycle_lock:
            # Проверяем отдельно подписку и обработчики от предыдущего запуска.
            if self._consumer_tag is not None:
                raise RuntimeError("Обработчик очереди уже запущен")
            if self._active_tasks:
                raise RuntimeError("Предыдущие обработчики сообщений ещё выполняются")
            if no_ack and not self._auto_ack:
                raise ValueError("no_ack несовместим с ручным подтверждением")
            consume_arguments = dict(arguments or {})
            if priority is not None:
                if "x-priority" in consume_arguments:
                    raise ValueError("Приоритет задан и в priority, и в arguments")
                consume_arguments["x-priority"] = priority

            await self._channel.set_qos(
                prefetch_count=prefetch_count,
                prefetch_size=prefetch_size,
                global_=global_,
                timeout=qos_timeout,
            )

            self._no_ack = no_ack
            self._consumer_tag = await self._queue.consume(
                self._on_message,
                no_ack=no_ack,
                exclusive=exclusive,
                arguments=consume_arguments or None,
                consumer_tag=consumer_tag,
                timeout=timeout,
                robust=robust,
            )

    async def _on_message(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        """Учесть активную задачу, чтобы stop() мог дождаться её завершения."""
        task = asyncio.current_task()
        if task is not None:
            self._active_tasks.add(task)

        try:
            await self._process_message(message)
        finally:
            if task is not None:
                self._active_tasks.discard(task)

    async def _process_message(self, message: AbstractIncomingMessage) -> None:
        """Проверить формат → вызвать обработчик → подтвердить результат."""
        # 1. Невалидное сообщение до пользовательского обработчика не доходит.
        try:
            event = self._event_type.model_validate_json(message.body)
        except ValueError:
            logger.exception("Неверный формат события %s", self._event_type.__name__)
            await self._reject_message(message, requeue=self._requeue_on_invalid)
            return

        # 2. Вызываем выбранный при создании объекта обработчик.
        try:
            if self._message_handler is not None:
                await self._message_handler(event, message)
            elif self._handler is not None:
                await self._handler(event)
        except Exception:
            logger.exception("Ошибка обработки события %s", event.event_id)
            if self._auto_ack:
                await self._reject_message(message, requeue=self._requeue_on_error)
            return

        # 3. В ручном режиме библиотека оставляет подтверждение обработчику.
        if not self._auto_ack:
            return
        if self._no_ack:
            return
        if message.processed:
            return
        await message.ack()

    async def _reject_message(
        self,
        message: AbstractIncomingMessage,
        *,
        requeue: bool,
    ) -> None:
        """Отклонить сообщение, только если оно ещё ждёт подтверждения."""
        if self._no_ack:
            return
        if message.processed:
            return
        await message.reject(requeue=requeue)

    async def stop(
        self,
        *,
        timeout: float | None = 30.0,
        cancel_timeout: float | None = None,
        nowait: bool = False,
    ) -> None:
        """Отменить подписку и дождаться активных обработчиков.

        cancel_timeout ограничивает ожидание ответа брокера об отмене подписки.
        timeout ограничивает ожидание обработчиков. При его истечении задачи
        продолжают работать: можно повторить stop() или закрыть канал.
        nowait=True отключает ожидание ответа брокера об отмене подписки.
        """
        if asyncio.current_task() in self._active_tasks:
            raise RuntimeError("Вызывайте stop() вне обработчика сообщения")
        async with self._lifecycle_lock:
            if self._consumer_tag is not None:
                await self._queue.cancel(
                    self._consumer_tag,
                    timeout=cancel_timeout,
                    nowait=nowait,
                )
                self._consumer_tag = None

            if not self._active_tasks:
                return

            # Снимок нужен, поскольку завершившиеся задачи удаляют себя из набора.
            active_handlers = tuple(self._active_tasks)
            _, unfinished_handlers = await asyncio.wait(
                active_handlers, timeout=timeout
            )
            if unfinished_handlers:
                raise TimeoutError(
                    f"Ещё выполняются обработчики: {len(unfinished_handlers)}"
                )
