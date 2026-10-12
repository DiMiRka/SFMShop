# Очередь сообщений в SFMShop

Сервисы после изменения данных публикуют события в RabbitMQ, консьюмер обрабатывает их асинхронно\
Сейчас события сбрасывают кэш в Redis, пишутся в журнал событий в MongoDB и запускают уведомление об оплаченном заказе\
Код: `sfmshop/services/queue_producer.py` и `sfmshop/services/queue_consumer.py`

## Поток

```text
POST /v1/orders → OrderService → commit заказа → publish order.created ─────────────┐
                              → commit оплаты → publish order.paid / payment_failed ─┴→ order_exchange
                                                                                         ├→ cache_queue        → сброс кэша
                                                                                         ├→ event_log_queue    → журнал в MongoDB
                                                                                         └→ notification_queue → уведомление (только order.paid)
```

Каждый сервис меняет данные внутри `async with db.begin()` и публикует событие только после выхода из блока, то есть после коммита\
Иначе консьюмер мог бы сбросить кэш раньше коммита, и параллельное чтение снова закэшировало бы старые данные на время TTL\
Порядок «коммит, потом событие» проверяет тест `test_event_is_published_only_after_commit` для событий товаров, пользователей и заказов,
а создание заказа публикует два события, каждое после своей транзакции

## События

Три exchange типа `direct`, все `durable`:

| Exchange | Routing key | Кто публикует | Тело |
| --- | --- | --- | --- |
| `product_exchange` | `product.created`, `product.updated`, `product.deleted` | `ProductService` | `product_ids` |
| `product_exchange` | `review.created`, `review.updated`, `review.deleted` | `ReviewService` | `review_ids`, `product_ids`, `user_ids` |
| `user_exchange` | `user.created`, `user.updated`, `user.deleted` | `UserService` | `user_ids`; при удалении ещё `order_ids` и `product_ids` |
| `order_exchange` | `order.created`, `order.paid`, `order.payment_failed`, `order.cancelled`, `order.deleted` | `OrderService` | `order_ids`, `user_ids`, `product_ids` |

Сообщения отправляются с `delivery_mode=PERSISTENT` и переживают перезапуск брокера\
У каждого сообщения есть `message_id` и `timestamp`; при повторах публикации они не меняются, поэтому консьюмер журнала не записывает событие дважды

## Очереди

| Очередь | Подписка | Что делает |
| --- | --- | --- |
| `cache_queue` | все события выше | удаляет ключи кэша товаров, пользователей и заказов |
| `event_log_queue` | все события выше | пишет событие в журнал в MongoDB, см. [database.md](database.md) |
| `notification_queue` | `order.paid` | письмо покупателю об оплаченном заказе |

Изменение заказа сбрасывает кэш заказов, товаров (изменились остатки) и пользователей (изменился баланс)\
Изменение отзыва сбрасывает кэш карточки товара: в ней средний рейтинг и число отзывов

## Письмо об оплаченном заказе

`sfmshop/services/notification_service.py` (`OrderNotifier`) и `sfmshop/clients/email_client.py`

1. консьюмер `notification_queue` получает `order.paid` и берёт из него только id заказа
2. проверяет в Redis отметку `notification:order_paid:{id}` (если письмо уже уходило, сообщение просто подтверждается)
3. читает заказ, товары и email покупателя из primary (в событии нет персональных данных,
   потому что тело события целиком сохраняется в журнал MongoDB)
4. отправляет письмо (текст и HTML) через SMTP и ставит отметку на 7 дней

- **Повторная доставка**\
  RabbitMQ доставляет сообщение хотя бы один раз, отметка в Redis не даёт отправить письмо дважды\
  Если Redis недоступен, письмо всё равно уходит (лучше редкий дубль, чем потерянное письмо)
- **SMTP недоступен**\
  Ошибка отправки уводит сообщение в `notification_queue.retry`, после трёх попыток в `notification_queue.error`\
  Отметка ставится только после успешной отправки
- **SMTP не настроен**\
  Без `SMTP_HOST` письма не отправляются, в лог пишется причина
- **Метрика**\
  `sfmshop_emails_total` с меткой `result` (`sent`, `failed`, `duplicate`, `disabled`, `skipped`)

В Docker Compose письма уходят в Mailpit (http://localhost:8025), в CI интеграционный тест проверяет письмо через API Mailpit

## Producer

`QueueProducer` один на приложение, создаётся в lifespan\
Публикация best-effort: операция уже закоммичена, поэтому ошибка брокера её не отменяет

- до `RABBITMQ_MAX_RETRIES` попыток
- перед повтором задержка `RABBITMQ_BASE_DELAY * RABBITMQ_BACKOFF_MULTIPLIER ** n` и переподключение
- после всех неудач лог `event_publish_failed`, метод возвращает `False`, запрос пользователя завершается успешно

Цена такого решения: при долгой недоступности брокера кэш может отдавать устаревшие данные до истечения TTL (15 минут)

## Consumer

`QueueConsumer` запускается в lifespan внутри процесса API, `prefetch_count=10`\
Если RabbitMQ при старте недоступен, консьюмер повторяет подключение в фоне с паузой 1, 2, 4 … 30 секунд, пока не подключится\
Без этого очереди не объявлялись бы, а события уходили бы в exchange без привязок и терялись без ошибок\
Состояние консьюмера видно в `/health/ready` (`queue_consumer`), продюсер при проверке готовности переподключается сам

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

- обновление аналитики: выручка, топ товаров
- вызов payment-service по событию заказа, см. [microservice_architecture.md](microservice_architecture.md)
- алерт на рост длины `*.error` очередей
