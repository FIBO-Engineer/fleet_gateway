"""
Helper functions for publishing Redis pub/sub messages to trigger subscriptions.

Usage example:
    import redis.asyncio as redis
    from pubsub_helpers import publish_robot_update, publish_request_update

    r = redis.Redis(host='localhost', port=6379, decode_responses=True)

    # After updating robot data in Redis
    await publish_robot_update(r, "Lertvilai")

    # After updating request data in Redis
    await publish_request_update(r, "123e4567-e89b-12d3-a456-426614174000")
"""

import redis.asyncio as redis
from uuid import UUID


async def publish_robot_update(r: redis.Redis, robot_name: str) -> None:
    """
    Publish an update notification for a robot.

    This triggers the robot_updates subscription for the specified robot.
    Call this after updating robot data in Redis.

    Args:
        r: Redis client instance
        robot_name: Name of the robot that was updated
    """
    await r.publish(f"robot:{robot_name}:update", "updated")


async def publish_request_update(r: redis.Redis, request_uuid: UUID | str) -> None:
    """
    Publish an update notification for a request.

    This triggers the request_updates subscription for the specified request.
    Call this after updating request data in Redis.

    Args:
        r: Redis client instance
        request_uuid: UUID of the request that was updated (can be UUID or string)
    """
    await r.publish(f"request:{request_uuid}:update", "updated")
