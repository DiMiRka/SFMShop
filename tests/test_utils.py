from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.exchange_client import ExchangeRateClient


pytestmark = pytest.mark.anyio


@patch("src.services.exchange_client.httpx.AsyncClient")
async def test_function_with_external_dependency(mock_async_client):
    response = MagicMock()
    response.json.return_value = {"rates": {"RUB": 90.0}}
    response.raise_for_status.return_value = None

    client_instance = MagicMock()
    client_instance.get = AsyncMock(return_value=response)
    mock_async_client.return_value = client_instance

    client = ExchangeRateClient(base_url="https://rates.example.test", timeout=1, max_retries=1)
    rate = await client.get_exchange_rate("USD", "RUB")

    assert rate == 90.0
    mock_async_client.assert_called_once_with(timeout=1)
    client_instance.get.assert_awaited_once_with("https://rates.example.test/USD")
    response.raise_for_status.assert_called_once_with()
