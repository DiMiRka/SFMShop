import httpx


class PaymentClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def process_payment(self, order_id: int, amount: float):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/payments",
                    json={"order_id": order_id, "amount": amount},
                    timeout=5.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            print(f"Ошибка вызова payment-service: {e}")
            return None
