# Архитектура микросервисов для проекта SFMShop

## payment-service

### Ответственность сервиса

payment-service отвечает за:

* обработку платежей пользователей
* списание средств (логическое, без реального провайдера)
* хранение информации о платежах
* управление статусами платежей (pending, success, failed)
* обеспечение идемпотентности операций

Сервис НЕ отвечает за:

* управление пользователями
* управление заказами
* управление товарами

---

### Структура проекта

```
payment-service/
├── src/
│   ├── api/
│   │   └── payments.py          # endpoints
│   ├── core/
│   │   ├── config.py           # настройки
│   │   └── security.py         # (при необходимости)
│   ├── database/
│   │   ├── connection.py
│   │   └── models.py           # модель Payment
│   ├── schemas/
│   │   └── payments.py         # Pydantic схемы
│   ├── services/
│   │   └── payment_service.py  # бизнес-логика
│   ├── repositories/
│   │   └── payment_repository.py
│   └── main.py
│
├── alembic/
├── .env
├── Dockerfile
└── docker-compose.yml
```

---

### Модель данных (пример)

```
Payment:
- id: int
- order_id: int
- user_id: int
- amount: Decimal
- status: str (pending, success, failed)
- created_at: datetime
```

---

### Endpoints

#### 1. Создание платежа

```
POST /payments
```

Request:

```json
{
  "order_id": 1,
  "user_id": 10,
  "amount": 150.50
}
```

Response (успех):

```json
{
  "id": 100,
  "order_id": 1,
  "status": "success"
}
```

Response (ошибка):

```json
{
  "detail": "Недостаточно средств"
}
```

Логика:

* проверка входных данных
* вызов user-service для проверки баланса
* списание средств (через user-service)
* сохранение платежа
* возврат результата

---

#### 2. Получение платежа

```
GET /payments/{id}
```

Response:

```json
{
  "id": 100,
  "order_id": 1,
  "user_id": 10,
  "amount": 150.50,
  "status": "success",
  "created_at": "2026-04-16T12:00:00"
}
```

---

### Взаимодействие с другими сервисами

#### Основной сценарий (order → payment)

```
order-service → payment-service
```

#### Шаги:

1. Order Service создает заказ (status = PENDING)
2. Order Service вызывает:

```
POST /payments
```

Передает:

```json
{
  "order_id": 1,
  "user_id": 10,
  "amount": 150.50
}
```

---

### Взаимодействие с user-service

payment-service вызывает:

```
GET /users/{id}/balance
```

или

```
POST /users/{id}/withdraw
```

---

### Обработка ошибок

Возможные ошибки:

#### 1. Недостаточно средств

* возвращается 400 или 409
* статус платежа → failed

#### 2. Пользователь не найден

* 404

#### 3. Внутренняя ошибка

* 500

Формат ответа:

```json
{
  "detail": "Описание ошибки"
}
```

---

### Поток выполнения (sequence)

```
Order Service
    ↓
POST /payments
    ↓
Payment Service
    ↓
User Service (проверка / списание)
    ↓
Payment Service
    ↓
Ответ Order Service
```

---

### Развертывание

#### Порты

* payment-service: 8001
* main-service: 8000

---

#### Docker (пример)

```
payment-service:
  build: .
  ports:
    - "8001:8001"
  env_file:
    - .env
```

---

#### Конфигурация взаимодействия

В order-service:

```
PAYMENT_SERVICE_URL=http://payment-service:8001
```

Вызов:

```python
await http_client.post(
    f"{PAYMENT_SERVICE_URL}/payments",
    json=payload
)
```

---

### База данных

Отдельная БД для payment-service:

```
payment_db
```

Это обеспечивает:

* независимость сервиса
* масштабируемость
* отказоустойчивость

---

### Дополнительно (опционально)

* идемпотентность (через idempotency-key)
* retry при сетевых ошибках
* логирование платежей
* интеграция с внешними платежными системами

---

### Итог

payment-service:

* изолирован
* имеет свою БД
* взаимодействует через HTTP
* не содержит бизнес-логики других доменов

Это соответствует принципам микросервисной архитектуры и позволяет масштабировать систему независимо.
