import asyncio


async def validate_order(order_id: int) -> dict:
    await asyncio.sleep(1)
    return {"order_id": order_id, "valid": True}


async def reserve_items(order_id: int) -> dict:
    await asyncio.sleep(1.5)
    return {"order_id": order_id, "reserved": True}


async def verify_address(order_id: int) -> dict:
    await asyncio.sleep(0.5)
    return {"order_id": order_id, "address_valid": True}


async def process_order_tg(order_id: int) -> dict:
    result = {"order_id": order_id}

    try:
        async with asyncio.TaskGroup() as tg:
            task_validate = tg.create_task(validate_order(order_id))
            task_reserve = tg.create_task(reserve_items(order_id))
            task_address = tg.create_task(verify_address(order_id))

    except* ValueError as eg:
        result["status"] = "validation_error"
        result["errors"] = [str(e) for e in eg.exceptions]

    except* ConnectionError as eg:
        result["status"] = "service_error"
        result["errors"] = [str(e) for e in eg.exceptions]

    else:
        return {
            "order_id": order_id,
            "validation": task_validate.result(),
            "reservation": task_reserve.result(),
            "address": task_address.result(),
            "status": "ready"
        }

    return result


async def main():
    result = await process_order_tg(101)
    print(f"Результат: {result}")


asyncio.run(main())
