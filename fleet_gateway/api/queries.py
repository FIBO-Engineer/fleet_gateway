"""
GraphQL Query resolvers for Fleet Gateway.

Handles all read operations: fetching robots and requests from Redis.
"""

import strawberry
import redis.asyncio as redis
import json
from uuid import UUID

from .types import Robot, Request
from .deserializers import deserialize_robot, deserialize_request


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

        # Pass 1: Deserialize all robots (with empty holdings)
        robot_keys = await r.keys("robot:*")
        robot_lookup = {}

        for key in robot_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    robot = deserialize_robot(data)
                    robot_lookup[robot.name] = robot
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing robot {key}: {e}")
                    continue

        # Pass 2: Deserialize all requests and populate robot holdings
        request_keys = await r.keys("request:*")

        for key in request_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    request = deserialize_request(data, robot_lookup)
                    # Add request to its handler's holdings
                    if request.handler and request.handler.name in robot_lookup:
                        robot_lookup[request.handler.name].holdings.append(request)
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {key}: {e}")
                    continue

        return list(robot_lookup.values())

    @strawberry.field
    async def requests(self, info: strawberry.types.Info) -> list[Request]:
        """
        Get all requests.

        Returns:
            List of all warehouse requests
        """
        r: redis.Redis = info.context["redis"]

        # First get all robots for the lookup
        robot_keys = await r.keys("robot:*")
        robot_lookup = {}

        for key in robot_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    robot = deserialize_robot(data)
                    robot_lookup[robot.name] = robot
                except (KeyError, ValueError, json.JSONDecodeError):
                    continue

        # Get all request keys
        request_keys = await r.keys("request:*")
        requests = []

        for key in request_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    requests.append(deserialize_request(data, robot_lookup))
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {key}: {e}")
                    continue

        return requests

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
        data = await r.hgetall(f"robot:{name}")

        if not data:
            return None

        try:
            robot = deserialize_robot(data)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Error deserializing robot {name}: {e}")
            return None

        # Populate holdings by finding all requests handled by this robot
        request_keys = await r.keys("request:*")
        robot_lookup = {name: robot}

        for key in request_keys:
            req_data = await r.hgetall(key)
            if req_data and req_data.get('handler') == name:
                try:
                    request = deserialize_request(req_data, robot_lookup)
                    robot.holdings.append(request)
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {key}: {e}")
                    continue

        return robot

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
        data = await r.hgetall(f"request:{uuid}")

        if not data:
            return None

        # Get robot for the handler
        robot_lookup = {}
        if data.get('handler'):
            robot_data = await r.hgetall(f"robot:{data['handler']}")
            if robot_data:
                try:
                    robot_lookup[data['handler']] = deserialize_robot(robot_data)
                except (KeyError, ValueError, json.JSONDecodeError):
                    pass

        try:
            return deserialize_request(data, robot_lookup)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Error deserializing request {uuid}: {e}")
            return None
