import pytest
from loguru import logger



@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def log_messages():
    messages: list[str] = []
    handler_id = logger.add(lambda record: messages.append(record.record["message"]), level="DEBUG")
    yield messages
    logger.remove(handler_id)
