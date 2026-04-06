import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorCollection

from src.database.connection import mongo_client

mongo_db = mongo_client["sfmshop_logs"]
logs_collection = mongo_db["logs"]


class LogService:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def find_logs(self, query: dict | None = None, limit: int = 100):
        logs = self.collection.find(query).limit(limit)
        return [log async for log in logs]

    async def save_log(self, log_data):
        if 'timestamp' not in log_data:
            log_data['timestamp'] = datetime.now()

        result = await self.collection.insert_one(log_data)
        return str(result.inserted_id)

    async def get_all_logs(self):
        return await self.find_logs()

    async def get_error_logs(self):
        return await self.find_logs({"type": "error"})

    async def get_logs_by_type(self, log_type: str):
        return await self.find_logs({"type": log_type})

    async def get_logs_by_status_code(self, status_code: int):
        return await self.find_logs({"status_code": status_code})

    async def get_logs_by_ip(self, ip: str):
        return await self.find_logs({"ip": ip})

    async def get_logs_by_date_range(self, start_date: datetime, end_date: datetime):
        return await self.find_logs({
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            },
        })

    async def get_recent_logs(self, minutes: int = 10):
        time_threshold = datetime.now() - timedelta(minutes=minutes)

        return await self.find_logs({"timestamp": {"$gte": time_threshold}})

    async def count_logs_by_type(self):
        pipeline = [
            {"$group": {"_id": "$type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]

        logs = self.collection.aggregate(pipeline)
        return [log async for log in logs]

    async def count_logs_by_status_code(self):
        pipeline = [
            {"$match": {"status_code": {"$exists": True}}},
            {"$group": {"_id": "$status_code", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]

        logs = self.collection.aggregate(pipeline)
        return [log async for log in logs]

    async def get_logs_per_minute(self):
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d %H:%M",
                            "date": "$timestamp"
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]

        logs = self.collection.aggregate(pipeline)
        return [log async for log in logs]

    async def get_logs_per_hour(self):
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d %H:00",
                            "date": "$timestamp"
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]

        logs = self.collection.aggregate(pipeline)
        return [log async for log in logs]


log_service = LogService(logs_collection)

error_log = {
    "type": "error",
    "message": "Ошибка подключения к БД",
    "stack_trace": "..."
}

access_log = {
    "type": "access",
    "ip": "192.168.1.1",
    "endpoint": "/api/products",
    "method": "GET",
    "status_code": 200
}


async def main():

    await log_service.save_log(error_log)
    await log_service.save_log(access_log)

    print(await log_service.get_all_logs())
    print(await log_service.get_logs_by_type("access"))
    print(await log_service.get_recent_logs(30))


asyncio.run(main())
