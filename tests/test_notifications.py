from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prometheus_client import REGISTRY
from redis.exceptions import ConnectionError as RedisConnectionError

from sfmshop.clients.email_client import EmailClient, create_email_client
from sfmshop.core.config import AppSettings
from sfmshop.services import notification_service
from sfmshop.services.notification_service import OrderNotifier, build_order_paid_email
from sfmshop.services.queue_consumer import QueueConsumer
from tests.test_queue import FakeMessage


pytestmark = pytest.mark.anyio


def paid_order(product_name="Mouse"):
    return SimpleNamespace(
        id=42,
        total=Decimal("320.50"),
        user=SimpleNamespace(name="Dima", email="dima@test.com"),
        items=[
            SimpleNamespace(product=SimpleNamespace(name=product_name), quantity=2, total=Decimal("300.00")),
            SimpleNamespace(product=SimpleNamespace(name="Cable"), quantity=1, total=Decimal("20.5")),
        ],
    )


class MemoryCache:
    def __init__(self):
        self.store = {}
        self.ttls = {}
        self.broken = False

    async def get(self, key):
        if self.broken:
            raise RedisConnectionError("redis is down")
        return self.store.get(key)

    async def set(self, key, data, ttl=900):
        if self.broken:
            raise RedisConnectionError("redis is down")
        self.store[key] = data
        self.ttls[key] = ttl


class Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def orders(monkeypatch):
    found = {42: paid_order()}

    class Repo:
        def __init__(self, session):
            pass

        async def get_with_products_and_user(self, order_id):
            return found.get(order_id)

    monkeypatch.setattr(notification_service, "OrderRepository", Repo)
    return found


def emails(result):
    return REGISTRY.get_sample_value("sfmshop_emails_total", {"result": result}) or 0


def notifier(cache, email):
    return OrderNotifier(Session, cache, email)


def test_email_lists_items_with_rubles_and_escapes_html():
    message = build_order_paid_email(paid_order(product_name="<b>Mouse</b>"))

    assert message["To"] == "dima@test.com"
    assert message["Subject"] == "Заказ №42 оплачен"
    text = message.get_body(("plain",)).get_content()
    html = message.get_body(("html",)).get_content()
    assert "- <b>Mouse</b> × 2: 300.00 ₽" in text
    assert "- Cable × 1: 20.50 ₽" in text
    assert "Итого: 320.50 ₽" in text
    assert "&lt;b&gt;Mouse&lt;/b&gt;" in html and "<b>Mouse</b>" not in html


async def test_paid_order_email_is_sent_once(orders):
    cache, email = MemoryCache(), SimpleNamespace(send=AsyncMock())
    sent, duplicate = emails("sent"), emails("duplicate")
    service = notifier(cache, email)

    await service.order_paid(42)
    await service.order_paid(42)

    email.send.assert_awaited_once()
    assert email.send.await_args.args[0]["To"] == "dima@test.com"
    assert cache.ttls == {"notification:order_paid:42": 7 * 24 * 3600}
    assert emails("sent") == sent + 1
    assert emails("duplicate") == duplicate + 1


async def test_smtp_failure_is_raised_for_retry_and_not_marked(orders):
    cache = MemoryCache()
    email = SimpleNamespace(send=AsyncMock(side_effect=OSError("smtp is down")))
    failed = emails("failed")

    with pytest.raises(OSError):
        await notifier(cache, email).order_paid(42)

    assert cache.store == {}
    assert emails("failed") == failed + 1


async def test_email_is_still_sent_when_redis_is_down(orders):
    cache, email = MemoryCache(), SimpleNamespace(send=AsyncMock())
    cache.broken = True

    await notifier(cache, email).order_paid(42)

    email.send.assert_awaited_once()


async def test_missing_order_and_disabled_smtp_send_nothing(orders):
    cache, email = MemoryCache(), SimpleNamespace(send=AsyncMock())
    skipped, disabled = emails("skipped"), emails("disabled")

    await notifier(cache, email).order_paid(999)
    await notifier(cache, None).order_paid(42)

    email.send.assert_not_awaited()
    assert cache.store == {}
    assert emails("skipped") == skipped + 1
    assert emails("disabled") == disabled + 1


async def test_failed_email_goes_to_retry_queue(orders):
    consumer = QueueConsumer(cache=None, url="amqp://test",
                             notifier=notifier(MemoryCache(), SimpleNamespace(send=AsyncMock(side_effect=OSError))))
    consumer.channel = SimpleNamespace(default_exchange=SimpleNamespace(publish=AsyncMock()))
    message = FakeMessage("order.paid", {"order_ids": 42}, retries=1)

    await consumer.process_notification(message)

    message.reject.assert_awaited_once_with(requeue=False)
    message.ack.assert_not_awaited()


async def test_email_client_passes_smtp_settings_to_transport():
    transport = AsyncMock()
    client = EmailClient("smtp.test", 2525, "Shop <shop@test>", username="u", password="p",
                         start_tls=False, timeout=3.0, transport=transport)
    message = build_order_paid_email(paid_order())

    await client.send(message)

    transport.assert_awaited_once_with(message, hostname="smtp.test", port=2525, username="u", password="p",
                                       start_tls=False, timeout=3.0)
    assert message["From"] == "Shop <shop@test>"


def test_email_client_is_created_only_with_smtp_host():
    assert create_email_client(AppSettings(smtp_host=None)) is None

    client = create_email_client(AppSettings(smtp_host="mailpit", smtp_port=1025, smtp_start_tls=False))

    assert client is not None
    assert (client.host, client.port, client.start_tls) == ("mailpit", 1025, False)
