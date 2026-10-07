# Очередь сообщений в SFMShop

Сервисы после изменения данных публикуют события в RabbitMQ, консьюмер обрабатывает их асинхронно\
Сейчас события сбрасывают кэш в Redis, пишутся в журнал событий в MongoDB и запускают уведомление о новом заказе\
Код: `src/services/queue_producer.py` и `src/services/queue_consumer.py`

## Поток

```text
POST /v1/orders → OrderService → commit в БД → publish order.created → order_exchange
                                                                          ├→ cache_queue        → сброс кэша
                                                                          ├→ event_log_queue    → журнал в MongoDB
                                                                          └→ notification_queue → уведомление
```

Каждый сервис меняет данные внутри `async with db.begin()` и публикует событие только после выхода из блока, то есть после коммита\
Иначе консьюмер мог бы сбросить кэш раньше коммита, и параллельное чтение снова закэшировало бы старые данные на время TTL\
Порядок «коммит, потом событие» проверяет тест `test_event_is_published_only_after_commit` для всех восьми событий

## События

Три exchange типа `direct`, все `durable`:

| Exchange | Routing key | Кто публикует | Тело |
| --- | --- | --- | --- |
| `product_exchange` | `product.created`, `product.updated`, `product.deleted` | `ProductService` | `product_ids` |
| `user_exchange` | `user.created`, `user.updated`, `user.deleted` | `UserService` | `user_ids`; при удалении ещё `order_ids` и `product_ids` |
| `order_exchange` | `order.created`, `order.deleted` | `OrderService` | `order_ids`, `user_ids`, `product_ids` |

Сообщения отправляются с `delivery_mode=PERSISTENT` и переживают перезапуск брокера\
У каждого сообщения есть `message_id` и `timestamp`; при повторах публикации они не меняются, поэтому консьюмер журнала не записывает событие дважды

## Очереди

| Очередь | Подписка | Что делает |
| --- | --- | --- |
| `cache_queue` | все события выше | удаляет ключи кэша товаров, пользователей и заказов |
| `event_log_queue` | все события выше | пишет событие в журнал в MongoDB, см. [database.md](database.md) |
| `notification_queue` | `order.created` | уведомление о заказе (сейчас запись в лог вместо email) |

Изменение заказа сбрасывает кэш заказов, товаров (изменились остатки) и пользователей (изменился баланс)

## Producer

`QueueProducer` один на приложение, создаётся в lifespan\
Публикация best-effort: операция уже закоммичена, поэтому ошибка брокера её не отменяет

- до `RABBITMQ_MAX_RETRIES` попыток
- перед повтором задержка `RABBITMQ_BASE_DELAY * RABBITMQ_BACKOFF_MULTIPLIER ** n` и переподключение
- после всех неудач лог `event_publish_failed`, метод возвращает `False`, запрос пользователя завершается успешно

Цена такого решения: при долгой недоступности брокера кэш может отдавать устаревшие данные до истечения TTL (15 минут)

## Consumer

`QueueConsumer` запускается в lifespan внутри процесса API, `prefetch_count=10`

Надёжность обработки:

- сообщение подтверждается только после успешной обработки
- при ошибке консьюмер сам делает `reject`, и сообщение уходит в `<очередь>.retry`, а через 5 секунд (TTL + dead letter) возвращается обратно.\
  Поэтому обработка идёт в `message.process(ignore_processed=True)`: без этого флага контекст после ручного `reject` пытается сделать `ack` и падает
- число попыток считается по заголовку `x-death`
- после 3 неудачных попыток сообщение переносится в `<очередь>.error` для разбора вручную.\
  В error-очереди сохраняются `message_id`, `timestamp` и исходный routing key (заголовок `x-original-routing-key`), поэтому сообщение можно отправить повторно
- повторная обработка безопасна: удаление ключа кэша идемпотентно, журнал пишет по `message_id` через upsert

```text
cache_queue ──ошибка──→ cache_queue.retry ──5 сек──→ cache_queue
     └──3 неудачи──→ cache_queue.error
```

## Масштабирование

- консьюмеров можно запустить несколько: RabbitMQ раздаёт сообщения из очереди между ними
- при росте нагрузки консьюмер выносится из процесса API в отдельный deployment
- очередь сглаживает пики: сообщения ждут в брокере, а не теряются

## Развитие

- email-уведомления вместо записи в лог
- обновление аналитики: выручка, топ товаров
- вызов payment-service по событию заказа, см. [microservice_architecture.md](microservice_architecture.md)
- алерт на рост длины `*.error` очередей
