"""
Request Store - Centralized request management and persistence.

Handles all request CRUD operations, persistence to Redis, and request lifecycle management.
"""

import redis.asyncio as redis
from uuid import UUID
from typing import TYPE_CHECKING

from fleet_gateway.api.types import Request
from fleet_gateway.helpers.serializers import request_to_dict
from fleet_gateway.enums import OrderStatus

if TYPE_CHECKING:
    from fleet_gateway.job_store import JobStore


class RequestStore():
    """Centralized request management and persistence"""

    def __init__(self, redis_client: redis.Redis):
        """Initialize RequestStore with Redis client"""
        self.redis = redis_client

    async def upsert_request(self, request: Request) -> str:
        """Insert or update request in Redis at request:{uuid} and return UUID"""
        request_data = request_to_dict(request)
        await self.redis.hset(f"request:{request.uuid}", mapping=request_data)
        await self.redis.publish(f"request:{request.uuid}:update", "updated")
        return str(request.uuid)

    async def upsert_all(self, requests: list[Request], job_store: "JobStore") -> list[str]:
        """
        Batch upsert multiple requests along with their associated jobs.

        This method will:
        1. Upsert all pickup jobs for all requests
        2. Upsert all delivery jobs for all requests
        3. Upsert all requests
        4. Publish update notifications

        Args:
            requests: List of Request objects to upsert
            job_store: JobStore instance to persist jobs

        Returns:
            List of request UUIDs that were upserted
        """
        request_uuids = []

        # Use Redis pipeline for efficient batch operations
        async with self.redis.pipeline(transaction=False) as pipe:
            for request in requests:
                # Upsert pickup and delivery jobs
                await job_store.upsert_job(request.pickup)
                await job_store.upsert_job(request.delivery)

                # Upsert request
                request_data = request_to_dict(request)
                pipe.hset(f"request:{request.uuid}", mapping=request_data)
                pipe.publish(f"request:{request.uuid}:update", "updated")
                request_uuids.append(str(request.uuid))

            # Execute all pipeline commands
            await pipe.execute()

        return request_uuids

    async def get_request(self, request_uuid: str | UUID, job_store: "JobStore") -> Request | None:
        """Fetch request from Redis by UUID, including full job objects"""
        if isinstance(request_uuid, UUID):
            request_uuid = str(request_uuid)

        request_data = await self.redis.hgetall(f"request:{request_uuid}")
        if not request_data:
            return None

        # Convert bytes to strings if needed
        request_dict = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in request_data.items()
        }

        # Fetch full job objects from JobStore
        pickup_job = await job_store.get_job(request_dict['pickup'])
        delivery_job = await job_store.get_job(request_dict['delivery'])

        if not pickup_job or not delivery_job:
            raise ValueError(f"Jobs not found for request {request_uuid}")

        return Request(
            uuid=UUID(request_dict['uuid']),
            pickup=pickup_job,
            delivery=delivery_job,
            handling_robot=None,  # Resolved separately via robot name lookup
            status=OrderStatus(int(request_dict['request_status']))
        )

    async def update_request_status(self, request_uuid: str | UUID, status) -> bool:
        """Update request status and publish update notification"""
        if isinstance(request_uuid, UUID):
            request_uuid = str(request_uuid)

        # Check if request exists
        exists = await self.redis.exists(f"request:{request_uuid}")
        if not exists:
            return False

        # Update status
        await self.redis.hset(f"request:{request_uuid}", "request_status", status.value)
        await self.redis.publish(f"request:{request_uuid}:update", "updated")
        return True

    async def update_request_handler(self, request_uuid: str | UUID, handler_name: str | None) -> bool:
        """Update request handler (robot name) and publish update notification"""
        if isinstance(request_uuid, UUID):
            request_uuid = str(request_uuid)

        # Check if request exists
        exists = await self.redis.exists(f"request:{request_uuid}")
        if not exists:
            return False

        # Update handler
        await self.redis.hset(f"request:{request_uuid}", "handler", handler_name or '')
        await self.redis.publish(f"request:{request_uuid}:update", "updated")
        return True

    async def delete_request(self, request_uuid: str | UUID) -> bool:
        """Remove request from Redis, return True if deleted"""
        if isinstance(request_uuid, UUID):
            request_uuid = str(request_uuid)

        result = await self.redis.delete(f"request:{request_uuid}")
        return result > 0

    async def exists(self, request_uuid: str | UUID) -> bool:
        """Check if request exists in Redis"""
        if isinstance(request_uuid, UUID):
            request_uuid = str(request_uuid)

        return await self.redis.exists(f"request:{request_uuid}") > 0

    async def get_all_request_uuids(self) -> list[str]:
        """Get all request UUIDs in Redis"""
        request_keys = await self.redis.keys("request:*")
        return [
            key.decode().split(':', 1)[1] if isinstance(key, bytes) else key.split(':', 1)[1]
            for key in request_keys
        ]

    async def get_all_requests(self, job_store: "JobStore") -> list[Request]:
        """Get all requests from Redis"""
        requests = []
        request_keys = await self.redis.keys("request:*")

        for key in request_keys:
            # Extract UUID from key (format: "request:uuid")
            if isinstance(key, bytes):
                key_str = key.decode()
            else:
                key_str = key

            request_uuid = key_str.split(':', 1)[1]
            request = await self.get_request(request_uuid, job_store)
            if request:
                requests.append(request)

        return requests

    async def get_requests_by_status(self, status, job_store: "JobStore") -> list[Request]:
        """Get all requests with a specific status"""
        all_requests = await self.get_all_requests(job_store)
        return [req for req in all_requests if req.status == status]

    async def get_requests_by_handler(self, handler_name: str, job_store: "JobStore") -> list[Request]:
        """Get all requests assigned to a specific robot handler"""
        requests = []
        request_keys = await self.redis.keys("request:*")

        for key in request_keys:
            request_data = await self.redis.hgetall(key)
            if request_data:
                # Convert bytes to strings
                request_dict = {
                    k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in request_data.items()
                }

                # Check if this request belongs to the handler
                if request_dict.get('handler') == handler_name:
                    request_uuid = request_dict['uuid']
                    request = await self.get_request(request_uuid, job_store)
                    if request:
                        requests.append(request)

        return requests
