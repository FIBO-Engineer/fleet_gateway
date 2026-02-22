"""
Order Store - Centralized Job & Request management and persistence.

Handles all request CRUD operations, persistence to Redis, and request lifecycle management.
"""

import redis.asyncio as redis
from uuid import UUID

from fleet_gateway.api.types import Request, OrderStatus, Job
from fleet_gateway.helpers.serializers import request_to_dict, job_to_dict
from fleet_gateway.helpers.deserializers import dict_to_request, dict_to_job

class OrderStore():
    def __init__(self, redis_client: redis.Redis):
        """Initialize OrderStore with Redis client"""
        self.redis = redis_client
    
    async def set_request(self, request: Request) -> bool:
        return await self.redis.hset(f"request:{str(request.uuid)}", mapping=request_to_dict(request)) > 0
    
    async def get_request_status(self, request: Request) -> OrderStatus:
        pickup_job: Job = await self.get_job(request.pickup_uuid)
        delivery_job: Job = await self.get_job(request.delivery_uuid)
        if pickup_job is None or delivery_job is None:
            raise RuntimeError("pickup_job or delivery_job not existed")
        
        pickup_status = pickup_job.status
        delivery_status = delivery_job.status

        # 1. Terminal failure states take highest priority
        if pickup_status == OrderStatus.FAILED or delivery_status == OrderStatus.FAILED:
            return OrderStatus.FAILED

        if pickup_status == OrderStatus.CANCELED or delivery_status == OrderStatus.CANCELED:
            return OrderStatus.CANCELED

        # 2. If both completed -> request completed
        if pickup_status == OrderStatus.COMPLETED and delivery_status == OrderStatus.COMPLETED:
            return OrderStatus.COMPLETED

        # 3. If either is currently running -> request in progress
        if pickup_status == OrderStatus.IN_PROGRESS or delivery_status == OrderStatus.IN_PROGRESS:
            return OrderStatus.IN_PROGRESS

        # 4. Otherwise still waiting
        return OrderStatus.QUEUING

    async def get_request(self, uuid: UUID) -> Request | None:
        return dict_to_request(uuid, await self.redis.hgetall(f"request:{str(uuid)}"))
    
    async def get_requests(self) -> list[Request]:
        keys = [k async for k in self.redis.scan_iter(match="request:*")]
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.hgetall(key)
        return [request for k, d in zip(keys, await pipe.execute()) if (request:=dict_to_request(UUID(k.split(":", 1)[1]), d)) is not None]

    async def set_job(self, job: Job) -> bool:
        return await self.redis.hset(f"job:{str(job.uuid)}", mapping=job_to_dict(job)) > 0

    async def get_job(self, uuid: UUID) -> Job | None:
        return dict_to_job(uuid, await self.redis.hgetall(f"job:{str(uuid)}"))

    async def get_jobs(self) -> list[Job]:
        keys = [k async for k in self.redis.scan_iter(match="job:*")]
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.hgetall(key)
        return [job for k, d in zip(keys, await pipe.execute()) if (job:=dict_to_job(UUID(k.split(":", 1)[1]), d)) is not None]
