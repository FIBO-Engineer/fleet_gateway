"""
Job Store - Centralized job management and persistence.

Handles all job CRUD operations, persistence to Redis, and job lifecycle management.
"""

import json
import redis.asyncio as redis

from fleet_gateway.api.types import Job
from fleet_gateway.helpers.serializers import job_to_dict, dict_to_job


class JobStore:
    """Centralized job management and persistence"""

    def __init__(self, redis_client: redis.Redis):
        """Initialize JobStore with Redis client"""
        self.redis = redis_client

    async def upsert_job(self, job: Job) -> str:
        """Insert or update job in Redis at job:{uuid} and return UUID"""
        job_data = job_to_dict(job)
        await self.redis.hset(f"job:{job.uuid}", mapping=job_data)
        await self.redis.publish(f"job:{job.uuid}:update", "updated")
        return job.uuid

    async def get_job(self, job_uuid: str) -> Job | None:
        """Fetch job from Redis by UUID"""
        job_data = await self.redis.hgetall(f"job:{job_uuid}")
        if not job_data:
            return None

        # Convert bytes to strings if needed
        job_dict = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in job_data.items()
        }

        # Parse nodes JSON string
        job_dict['nodes'] = json.loads(job_dict['nodes'])
        return dict_to_job(job_dict)

    async def update_job_operation(self, job_uuid: str, operation) -> bool:
        """Update job operation and publish update notification"""
        # Check if job exists
        exists = await self.redis.exists(f"job:{job_uuid}")
        if not exists:
            return False

        # Update operation
        await self.redis.hset(f"job:{job_uuid}", "operation", operation.value)
        await self.redis.publish(f"job:{job_uuid}:update", "updated")
        return True

    async def update_job_request_uuid(self, job_uuid: str, request_uuid: str | None) -> bool:
        """Update job's associated request UUID and publish update notification"""
        # Check if job exists
        exists = await self.redis.exists(f"job:{job_uuid}")
        if not exists:
            return False

        # Update request_uuid
        await self.redis.hset(f"job:{job_uuid}", "request_uuid", request_uuid or '')
        await self.redis.publish(f"job:{job_uuid}:update", "updated")
        return True

    async def delete_job(self, job_uuid: str) -> bool:
        """Remove job from Redis, return True if deleted"""
        result = await self.redis.delete(f"job:{job_uuid}")
        return result > 0

    async def exists(self, job_uuid: str) -> bool:
        """Check if job exists in Redis"""
        return await self.redis.exists(f"job:{job_uuid}") > 0

    async def get_all_job_uuids(self) -> list[str]:
        """Get all job UUIDs in Redis"""
        job_keys = await self.redis.keys("job:*")
        return [
            key.decode().split(':', 1)[1] if isinstance(key, bytes) else key.split(':', 1)[1]
            for key in job_keys
        ]

    async def get_all_jobs(self) -> list[Job]:
        """Get all jobs from Redis"""
        jobs = []
        job_keys = await self.redis.keys("job:*")

        for key in job_keys:
            job_data = await self.redis.hgetall(key)
            if job_data:
                # Convert bytes to strings
                job_dict = {
                    k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in job_data.items()
                }
                job_dict['nodes'] = json.loads(job_dict['nodes'])
                jobs.append(dict_to_job(job_dict))

        return jobs

    async def get_jobs_for_request(self, request_uuid: str) -> list[Job]:
        """Get all jobs associated with a request UUID"""
        jobs = []
        job_keys = await self.redis.keys("job:*")

        for key in job_keys:
            job_data = await self.redis.hgetall(key)
            if job_data:
                # Convert bytes to strings
                job_dict = {
                    k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in job_data.items()
                }

                # Check if this job belongs to the request
                if job_dict.get('request_uuid') == request_uuid:
                    job_dict['nodes'] = json.loads(job_dict['nodes'])
                    jobs.append(dict_to_job(job_dict))

        return jobs

    async def get_jobs_by_operation(self, operation) -> list[Job]:
        """Get all jobs with a specific operation type"""
        all_jobs = await self.get_all_jobs()
        return [job for job in all_jobs if job.operation == operation]
