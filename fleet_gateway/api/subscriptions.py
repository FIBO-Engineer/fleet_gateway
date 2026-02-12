"""
GraphQL Subscription resolvers for Fleet Gateway.

Handles real-time updates via Redis pub/sub for robots and requests.
"""

import strawberry
import redis.asyncio as redis
import json
from typing import AsyncGenerator
from uuid import UUID

from .types import Robot, Request
from .deserializers import deserialize_robot, deserialize_request


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
            data = await r.hgetall(f"robot:{name}")
            if data:
                try:
                    robot = deserialize_robot(data)

                    # Populate holdings
                    request_keys = await r.keys("request:*")
                    robot_lookup = {name: robot}

                    for key in request_keys:
                        req_data = await r.hgetall(key)
                        if req_data and req_data.get('handler') == name:
                            try:
                                request = deserialize_request(req_data, robot_lookup)
                                robot.holdings.append(request)
                            except (KeyError, ValueError, json.JSONDecodeError):
                                continue

                    yield robot
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing robot {name}: {e}")
                    yield None
            else:
                yield None

            # Listen for updates
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Fetch updated robot data
                    data = await r.hgetall(f"robot:{name}")
                    if data:
                        try:
                            robot = deserialize_robot(data)

                            # Populate holdings
                            request_keys = await r.keys("request:*")
                            robot_lookup = {name: robot}

                            for key in request_keys:
                                req_data = await r.hgetall(key)
                                if req_data and req_data.get('handler') == name:
                                    try:
                                        request = deserialize_request(req_data, robot_lookup)
                                        robot.holdings.append(request)
                                    except (KeyError, ValueError, json.JSONDecodeError):
                                        continue

                            yield robot
                        except (KeyError, ValueError, json.JSONDecodeError) as e:
                            print(f"Error deserializing robot {name}: {e}")
                            yield None
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
            data = await r.hgetall(f"request:{uuid}")
            if data:
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
                    yield deserialize_request(data, robot_lookup)
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {uuid}: {e}")
                    yield None
            else:
                yield None

            # Listen for updates
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Fetch updated request data
                    data = await r.hgetall(f"request:{uuid}")
                    if data:
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
                            yield deserialize_request(data, robot_lookup)
                        except (KeyError, ValueError, json.JSONDecodeError) as e:
                            print(f"Error deserializing request {uuid}: {e}")
                            yield None
        finally:
            await pubsub.unsubscribe(f"request:{uuid}:update")
            await pubsub.close()
