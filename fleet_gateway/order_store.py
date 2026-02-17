"""
Order Store - Centralized Job & Request management and persistence.

Handles all request CRUD operations, persistence to Redis, and request lifecycle management.
"""

import redis.asyncio as redis
from uuid import UUID

from fleet_gateway.api.types import Request, RequestStatus, Job, JobOperation, Robot, Node

class OrderStore():
    def __init__(self, redis_client: redis.Redis):
        """Initialize OrderStore with Redis client"""
        self.redis = redis_client
    
    async def get_request(self, uuid: str) -> Request | None:
        status = await self.redis.hget(f"request:{uuid}", "status")

        if status is None:
            return None

        return Request(
            uuid=UUID(uuid),
            status=RequestStatus(int(status)),
        )
    
    async def get_requests(self) -> list[Request]:
        keys: list[str] = []
        async for key in self.redis.scan_iter(match="request:*"):
            keys.append(key)

        if not keys:
            return []
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.hget(key, "status")

        statuses = await pipe.execute()

        requests: list[Request] = []

        for key, status_raw in zip(keys, statuses):
            if status_raw is None:
                continue

            uuid = key.split(":", 1)[1]

            requests.append(
                Request(
                    uuid=UUID(uuid),
                    status=RequestStatus(int(status_raw)),
                )
            )
        return requests

    async def get_job(self, uuid) -> Job:
        operation = await self.redis.hget(f"job:{uuid}", "operation")

        if operation is None:
            return None

        return Job(
            uuid=UUID(uuid),
            operation=JobOperation(int(operation))
        )

    async def get_jobs(self) -> list[Job]:
        keys: list[str] = []
        async for key in self.redis.scan_iter(match="job:*"):
            keys.append(key)

        if not keys:
            return []
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.hget(key, "operation")

        operations = await pipe.execute()

        jobs: list[Job] = []

        for key, operation_raw in zip(keys, operations):
            if operation_raw is None:
                continue

            uuid = key.split(":", 1)[1]

            jobs.append(
                Request(
                    uuid=UUID(uuid),
                    status=RequestStatus(int(operation_raw)),
                )
            )
        return jobs

    async def get_pickup_job_by_request(self, root: Request) -> Job:
        raise NotImplementedError

    async def get_delievery_job_by_request(self, root: Request) -> Job:
        raise NotImplementedError

    async def get_handling_robot_by_request(self, root: Request) -> Robot | None:
        raise NotImplementedError

    async def get_target_node_by_job(self, root: Job) -> Node | None:
        raise NotImplementedError

    async def get_request_by_job(self, root: Job) -> Request | None:
        raise NotImplementedError

    async def get_handling_robot_by_job(self, root: Job) -> Robot:
        raise NotImplementedError