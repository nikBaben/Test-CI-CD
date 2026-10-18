# Правила проекта

## Структура и запуск

- Продуктовый код находится в `src/`. Единая точка входа API — `src/main.py`, ASGI-объект `src.main:app`.
- Используй абсолютные импорты от `src`: `from src.modules...` и `from src.shared...`. Относительные импорты и изменение `sys.path` внутри продуктового кода не используй.
- У каждого модуля свой `src/modules/<module>/infrastructure/bootstrap.py`: настройка HTTP и создание/закрытие ресурсов модуля.
- `src/main.py` объединяет bootstrap модулей; создание Keycloak, Checko, MinIO и RabbitMQ остаётся внутри соответствующего модуля.
- Общая инфраструктура PostgreSQL создаётся в `src/shared/database/bootstrap.py`. `.env` и миграции остаются в корне проекта.

## Имена use case

- Каждый use case размещай отдельным файлом в `application/use_cases/` соответствующего модуля.
- Имя файла: `<действие>_<сущность>_use_case.py` в snake_case. Например: `create_company_use_case.py`, `register_user_use_case.py`, `get_user_profile_use_case.py`.
- Имя класса должно точно соответствовать имени файла в PascalCase: `CreateCompanyUseCase`, `RegisterUserUseCase`, `GetUserProfileUseCase`.
- Не объединяй несколько use case в общие файлы вроде `auth.py`. В одном файле должен быть один класс use case.
- При добавлении или переименовании обновляй импорты, зависимости, аннотации, тесты, скрипты и документацию.
