# Подход к тестированию в проекте SFMShop

## Обзор

В проекте SFMShop тесты проверяют бизнес-логику, сервисный слой, API endpoints и интеграционные связи между компонентами\
Основная цель тестов быстро находить регрессии без обращения к реальным внешним зависимостям: PostgreSQL, Redis, RabbitMQ и внешним HTTP API

Актуальный результат запуска:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing
```

Результат: 38 тестов пройдены, общее покрытие 92%

## Типы тестов

### Unit-тесты моделей

Файл: `tests/test_models.py`

Покрывает:

- создание `Product`, `User`, `Order`;
- расчет полной стоимости заказа через `Order.calculate_total`;
- расчет скидки через `OrderCalculator.calculate_discount`;
- расчет доставки через `OrderCalculator.calculate_delivery`.

В тестах используются фикстуры из `tests/conftest.py`: `sample_product`, `sample_user`, `sample_order`.

Пример параметризации:

```python
@pytest.mark.parametrize(
    "discount_percent,expected",
    [
        (0, 45000),
        (5, 42750),
        (10, 40500),
        (15, 38250),
        (100, 0),
    ],
)
def test_calculate_discount_all_cases(sample_order, discount_percent, expected):
    assert OrderCalculator.calculate_discount(sample_order, discount_percent) == expected
```

### Unit-тест внешней зависимости

Файл: `tests/test_utils.py`

Покрывает:

- `ExchangeRateClient.get_exchange_rate`;
- изоляция от реального HTTP API через `unittest.mock.patch`;
- проверка что внешний клиент `httpx.AsyncClient` вызывается с ожидаемыми параметрами

Тест не выполняет реальный сетевой запрос, вместо этого мокается использование зависимости:

```python
@patch("src.services.exchange_client.httpx.AsyncClient")
async def test_function_with_external_dependency(mock_async_client):
    ...
```

### Unit-тесты сервиса заказа с моками

Файл: `tests/test_main_order_service.py`

Покрывает реальный `src.services.order_service.OrderService`.

Проверяются сценарии:

- успешное создание заказа, где `order_id = 42`;
- ошибка на пустом заказе;
- падение БД через `side_effect`;
- гарантия что событие в очередь не отправляется, если создание заказа в БД упало

Для изоляции используются `MagicMock` и `AsyncMock`: репозитории, кэш и очередь не обращаются к реальным БД, Redis или RabbitMQ

### API-тесты с моками

Файл: `tests/test_api.py`

Покрывает реальные endpoints FastAPI:

- `GET /v1/products/`;
- `POST /v1/orders/`

Вместо реальных зависимостей используются `app.dependency_overrides`:

- `get_product_read_service` заменяется мок-сервисом;
- `get_order_write_service` заменяется мок-сервисом;
- `get_current_user` заменяется тестовым пользователем

Так API тесты проверяют маршрутизацию, статусы ответов и контракт ответа, но не требуют реальной БД, Redis, RabbitMQ или авторизации

## Покрытие кода

Инструмент: `pytest-cov`.

Команда:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing
```

Достигнутое покрытие:

- общее покрытие `src`: 92%;
- `src.models.product`: 100%;
- `src.models.user`: 100%;
- `src.models.order`: 95%;
- `src.services.order_service`: 100%;
- `src.services.product_service`: 100%;
- `src.services.user_service`: 98%;
- `src.api.v1.products`: 100%;
- `src.api.v1.orders`: 100%;
- `src.api.v1.users`: 100%;
- `src.api.v1.auth`: 100%;
- `src.services.exchange_client`: 83%.


## Использованные техники

### TDD

Для новой бизнес проверки (к примеру для расчета стоимости заказа сначала зафиксирован ожидаемый сценарий в тесте)

### Фикстуры

Фикстуры используются для подготовки повторяющихся объектов (пользователя, товара и заказа)\
Это делает тесты короче и убирает дублирование создания данных.

### Параметризация

Параметризация используется для проверки нескольких вариантов расчета скидки и доставки одной тестовой функцией\
Такой подход хорошо подходит для расчетной логики

### Моки

Моки используются для изоляции от внешних зависимостей:

- `patch("src.services.exchange_client.httpx.AsyncClient")` изоляция от внешнего HTTP API;
- `MagicMock` и `AsyncMock` замена репозиториев, кэша и очереди в `OrderService`;
- `app.dependency_overrides` подмена FastAPI зависимостей в API-тестах

### Проверка ошибок через side_effect

В тесте падения БД используется `side_effect`:

```python
order_rep.create.side_effect = RuntimeError("DB error")
```

Это позволяет проверить негативный сценарий без реальной БД и убедиться что очередь не получает событие после ошибки

## Вывод

Тесты SFMShop организованы так, чтобы быстро проверять критичную бизнес-логику и API-контракты без реальных внешних сервисов\
Основной набор техник: фикстуры, параметризация, моки, `dependency_overrides` и `pytest-cov`\
Текущий уровень покрытия `92%` достаточен для учебного проекта и покрывает ключевые компоненты: модели, сервисы и API endpoints
