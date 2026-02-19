"""
Order Store - Centralized Job & Request management and persistence.

Handles all request CRUD operations, persistence to Redis, and request lifecycle management.
"""

import redis.asyncio as redis
from uuid import UUID

from fleet_gateway.api.types import Request, Job
from fleet_gateway.helpers.deserializers import dict_to_request, dict_to_job

class OrderStore():
    def __init__(self, redis_client: redis.Redis):
        """Initialize OrderStore with Redis client"""
        self.redis = redis_client
    
    async def get_request(self, uuid: UUID) -> Request | None:
        return dict_to_request(await self.redis.hgetall(f"request:{str(uuid)}"))
    
    async def get_requests(self) -> list[Request]:
        keys = [k async for k in self.redis.scan_iter(match="request:*")]
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.hgetall(key)
        return [request for d in await pipe.execute() if (request:=dict_to_request(d)) is not None]

    async def get_job(self, uuid: UUID) -> Job | None:
        return dict_to_job(await self.redis.hgetall(f"job:{str(uuid)}"))

    async def get_jobs(self) -> list[Job]:
        keys = [k async for k in self.redis.scan_iter(match="job:*")]
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.hgetall(key)
        return [job for d in await pipe.execute() if (job:=dict_to_job(d)) is not None]
