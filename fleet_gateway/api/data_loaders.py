"""
Shared data loading logic for GraphQL queries and subscriptions.

Provides reusable functions for fetching and deserializing robots and requests from Redis.
"""

import json
import redis.asyncio as redis
from uuid import UUID

from .types import Robot, Request
from .deserializers import deserialize_robot, deserialize_request


async def load_robot_lookup(r: redis.Redis) -> dict[str, Robot]:
    """
    Load all robots and return as a lookup dictionary.

    Args:
        r: Redis connection

    Returns:
        Dictionary mapping robot names to Robot objects
    """
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

    return robot_lookup


async def load_robot_with_holdings(r: redis.Redis, name: str) -> Robot | None:
    """
    Load a specific robot with its holdings populated.

    Args:
        r: Redis connection
        name: Robot name

    Returns:
        Robot with holdings if found, None otherwise
    """
    data = await r.hgetall(f"robot:{name}")

    if not data:
        return None

    try:
        robot = deserialize_robot(data)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"Error deserializing robot {name}: {e}")
        return None

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

    return robot


async def load_request(r: redis.Redis, uuid: UUID) -> Request | None:
    """
    Load a specific request with its handler robot populated.

    Args:
        r: Redis connection
        uuid: Request UUID

    Returns:
        Request if found, None otherwise
    """
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


async def load_all_robots_with_holdings(r: redis.Redis) -> list[Robot]:
    """
    Load all robots with their holdings populated.

    Args:
        r: Redis connection

    Returns:
        List of all robots in the system
    """
    # Pass 1: Deserialize all robots (with empty holdings)
    robot_lookup = await load_robot_lookup(r)

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


async def load_all_requests(r: redis.Redis) -> list[Request]:
    """
    Load all requests with their handler robots populated.

    Args:
        r: Redis connection

    Returns:
        List of all warehouse requests
    """
    # First get all robots for the lookup
    robot_lookup = await load_robot_lookup(r)

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


async def get_robot_current_node(r: redis.Redis, robot_name: str) -> int | None:
    """
    Get the current node ID where the robot is located.

    Args:
        r: Redis connection
        robot_name: Robot name

    Returns:
        Current node ID if found, None otherwise
    """
    robot_data = await r.hgetall(f"robot:{robot_name}")

    if not robot_data or 'mobile_base_status' not in robot_data:
        return None

    try:
        mobile_base_status = json.loads(robot_data['mobile_base_status'])
        return mobile_base_status['last_seen']['id']
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
