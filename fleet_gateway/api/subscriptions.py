"""
GraphQL Subscription resolvers for Fleet Gateway.

Handles real-time updates via Redis pub/sub for robots and requests.
"""

import strawberry
import redis.asyncio as redis
from typing import AsyncGenerator
from uuid import UUID

from .types import Robot, Request
from .data_loaders import load_robot_with_holdings, load_request


@strawberry.type
class Subscription:
    """GraphQL Subscription root"""

    @strawberry.subscription
    async def robot_updates(
        self,
        info: strawberry.types.Info,
        name: str
    ) -> AsyncGenerator[Robot | None, None]:
        """
        Subscribe to updates for a specific robot by name.

        Args:
            name: Robot name

        Yields:
            Robot state whenever it changes
        """
        r: redis.Redis = info.context["redis"]

        # Create a separate Redis connection for pub/sub
        pubsub = r.pubsub()
        await pubsub.subscribe(f"robot:{name}:update")

        try:
            # Send initial state
            yield await load_robot_with_holdings(r, name)

            # Listen for updates
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Fetch and yield updated robot data
                    yield await load_robot_with_holdings(r, name)
        finally:
            await pubsub.unsubscribe(f"robot:{name}:update")
            await pubsub.close()

    @strawberry.subscription
    async def request_updates(
        self,
        info: strawberry.types.Info,
        uuid: UUID
    ) -> AsyncGenerator[Request | None, None]:
        """
        Subscribe to updates for a specific request by UUID.

        Args:
            uuid: Request UUID

        Yields:
            Request state whenever it changes
        """
        r: redis.Redis = info.context["redis"]

        # Create a separate Redis connection for pub/sub
        pubsub = r.pubsub()
        await pubsub.subscribe(f"request:{uuid}:update")

        try:
            # Send initial state
            yield await load_request(r, uuid)

            # Listen for updates
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Fetch and yield updated request data
                    yield await load_request(r, uuid)
        finally:
            await pubsub.unsubscribe(f"request:{uuid}:update")
            await pubsub.close()
