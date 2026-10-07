# Выделение микросервиса: payment-service

Проект пока монолит: оплата заказа это списание с баланса пользователя внутри транзакции `OrderService.create_order`\
Документ описывает, как вынести оплату в отдельный payment-service\
В основном сервисе для этого уже есть заготовка клиента `src/clients/payment_client.py`

## Ответственность

payment-service отвечает за:

- обработку платежей пользователей
- списание средств (логическое, без реального платёжного провайдера)
- хранение платежей и их статусов: `pending`, `success`, `failed`
- идемпотентность: повтор запроса не списывает деньги второй раз

payment-service не отвечает за пользователей, заказы и товары

## Структура проекта

Слои те же, что в основном сервисе:

```text
payment-service/
├── src/
│   ├── api/v1/payments.py               # эндпоинты
│   ├── core/config.py                   # настройки
│   ├── database/
│   │   ├── connection.py
│   │   └── models.py                    # модель Payment
│   ├── schemas/payments.py              # Pydantic-схемы
│   ├── services/payment_service.py      # бизнес-логика
│   ├── repositories/payment_repository.py
│   └── main.py
├── alembic/
├── Dockerfile
└── docker-compose.yml
```

## Модель данных

```text
Payment:
- id: int
- order_id: int (уникальный, защита от двойной оплаты)
- user_id: int
- amount: Decimal
- status: pending | success | failed
- created_at: datetime
```

## Эндпоинты

### Создание платежа

`POST /api/v1/payments`

Запрос:

```json
{
  "order_id": 1,
  "user_id": 10,
  "amount": "150.50"
}
```

Ответ при успехе:

```json
{
  "id": 100,
  "order_id": 1,
  "status": "success"
}
```

Ответ при ошибке:

```json
{
  "detail": "Недостаточно средств"
}
```

Логика:

1. проверка входных данных
2. если платёж по этому `order_id` уже есть, вернуть его без нового списания
3. списание средств через user-service
4. сохранение платежа со статусом `success` или `failed`

Деньги передаются строкой, как в основном API, чтобы не терять точность на float

### Получение платежа

`GET /api/v1/payments/{id}`

```json
{
  "id": 100,
  "order_id": 1,
  "user_id": 10,
  "amount": "150.50",
  "status": "success",
  "created_at": "2026-04-16T12:00:00"
}
```

## Взаимодействие сервисов

```text
Order Service ──POST /api/v1/payments──→ Payment Service ──POST /users/{id}/withdraw──→ User Service
      ↑                                        │
      └──────────────── ответ ─────────────────┘
```

1. Order Service создаёт заказ со статусом `pending` (поле статуса заказа появится вместе с сервисом)
2. Order Service вызывает `POST /api/v1/payments`
3. Payment Service списывает средства через user-service: `GET /users/{id}/balance` и `POST /users/{id}/withdraw`
4. по ответу Order Service переводит заказ в `paid` или `failed`

`PaymentClient` в основном сервисе сейчас передаёт только `order_id` и `amount` числом\
При подключении сервиса его нужно привести к этому контракту

## Ошибки

| Ситуация | Код | Статус платежа |
| --- | --- | --- |
| недостаточно средств | 409 | `failed` |
| пользователь не найден | 404 | платёж не создаётся |
| внутренняя ошибка | 500 | `pending`, нужна повторная проверка |

Формат ответа тот же, что в основном API: `{"detail": "Описание ошибки"}`

## Развёртывание

- payment-service на порту 8001, основной сервис на 8000
- своя база `payment_db`: сервис не читает чужие таблицы и масштабируется отдельно

```yaml
payment-service:
  build: .
  ports:
    - "8001:8001"
  env_file:
    - .env
```

В основном сервисе адрес задаётся настройкой:

```text
PAYMENT_SERVICE_URL=http://payment-service:8001
```

```python
await http_client.post(f"{PAYMENT_SERVICE_URL}/api/v1/payments", json=payload)
```

## Надёжность

- идемпотентность по `order_id` (или заголовок `Idempotency-Key`)
- таймаут и повторы с экспоненциальной задержкой на сетевые ошибки и 5xx, как в клиенте курсов валют
- при недоступности сервиса заказ остаётся в `pending`, оплату можно повторить позже
- асинхронный вариант: Order Service публикует `order.created`, payment-service забирает событие из RabbitMQ.\
  Так основной сервис не ждёт ответа, но клиенту нужно узнавать статус оплаты отдельно

## Итог

payment-service изолирован, имеет свою БД, общается с другими сервисами по HTTP или через RabbitMQ
и не содержит логики других доменов\
Это позволяет масштабировать и развёртывать оплату независимо от остального магазина
