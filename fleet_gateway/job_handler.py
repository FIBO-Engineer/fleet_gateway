"""
Job Handler - Centralized job management and persistence.

Handles all job CRUD operations, persistence to Redis, and job lifecycle management.
"""

import json
import redis.asyncio as redis

from fleet_gateway.models import Job, job_to_dict, dict_to_job


class JobHandler:
    """Centralized job management and persistence"""

    def __init__(self, redis_client: redis.Redis):
        """Initialize JobHandler with Redis client"""
        self.redis = redis_client

    async def upsert_job(self, job: Job) -> str:
        """Insert or update job in Redis at job:{uuid} and return UUID"""
        job_data = job_to_dict(job)
        await self.redis.hset(f"job:{job.uuid}", mapping=job_data)
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

    async def delete_job(self, job_uuid: str) -> bool:
        """Remove job from Redis, return True if deleted"""
        result = await self.redis.delete(f"job:{job_uuid}")
        return result > 0

    async def get_jobs_for_request(self, request_uuid: str) -> list[Job]:
        """Find all jobs associated with a request UUID"""
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
