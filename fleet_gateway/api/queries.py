"""
GraphQL Query resolvers for Fleet Gateway.

Handles all read operations: fetching robots and requests from Redis.
"""

import strawberry
import redis.asyncio as redis
from uuid import UUID

from .types import Robot, Request
from .data_loaders import (
    load_all_robots_with_holdings,
    load_all_requests,
    load_robot_with_holdings,
    load_request
)


@strawberry.type
class Query:
    """GraphQL Query root"""

    @strawberry.field
    async def robots(self, info: strawberry.types.Info) -> list[Robot]:
        """
        Get all robots with their holdings.

        Returns:
            List of all robots in the system
        """
        r: redis.Redis = info.context["redis"]
        return await load_all_robots_with_holdings(r)

    @strawberry.field
    async def requests(self, info: strawberry.types.Info) -> list[Request]:
        """
        Get all requests.

        Returns:
            List of all warehouse requests
        """
        r: redis.Redis = info.context["redis"]
        return await load_all_requests(r)

    @strawberry.field
    async def robot(self, info: strawberry.types.Info, name: str) -> Robot | None:
        """
        Get a specific robot by name.

        Args:
            name: Robot name

        Returns:
            Robot if found, None otherwise
        """
        r: redis.Redis = info.context["redis"]
        return await load_robot_with_holdings(r, name)

    @strawberry.field
    async def request(self, info: strawberry.types.Info, uuid: UUID) -> Request | None:
        """
        Get a specific request by UUID.

        Args:
            uuid: Request UUID

        Returns:
            Request if found, None otherwise
        """
        r: redis.Redis = info.context["redis"]
        return await load_request(r, uuid)
