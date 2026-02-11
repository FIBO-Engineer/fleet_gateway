"""
Example dispatcher implementation showing how to send jobs to robots.

This demonstrates:
1. How to create and send jobs to robots
2. How to track request state in Redis
3. How to trigger subscription updates
"""

import asyncio
import json
from uuid import UUID, uuid4
import redis.asyncio as redis
from robot_handler import RobotHandler
from fleet_gateway.enums import WarehouseOperation, RequestStatus


async def create_request_in_redis(
    r: redis.Redis,
    pickup_nodes: list[dict],
    delivery_nodes: list[dict],
    handler_name: str
) -> str:
    """
    Create a new request in Redis.

    Args:
        r: Redis client
        pickup_nodes: List of nodes for pickup job
        delivery_nodes: List of nodes for delivery job
        handler_name: Name of the robot handling this request

    Returns:
        UUID string of the created request
    """
    request_uuid = str(uuid4())

    pickup_job = {
        'operation': WarehouseOperation.PICKUP.value,
        'nodes': pickup_nodes
    }

    delivery_job = {
        'operation': WarehouseOperation.DELIVERY.value,
        'nodes': delivery_nodes
    }

    request_data = {
        'uuid': request_uuid,
        'pickup': json.dumps(pickup_job),
        'delivery': json.dumps(delivery_job),
        'handler': handler_name,
        'request_status': str(RequestStatus.IN_PROGRESS.value)
    }

    await r.hset(f"request:{request_uuid}", mapping=request_data)
    await r.publish(f"request:{request_uuid}:update", "updated")

    return request_uuid


async def send_pickup_delivery_request(
    robot_handler: RobotHandler,
    r: redis.Redis,
    pickup_nodes: list[dict],
    delivery_nodes: list[dict]
):
    """
    Send a complete pickup and delivery request to a robot.

    Args:
        robot_handler: Robot handler instance
        r: Redis client
        pickup_nodes: List of nodes for pickup (e.g., [waypoint, shelf])
        delivery_nodes: List of nodes for delivery (e.g., [waypoint, depot])
    """
    # Create request in Redis
    request_uuid = await create_request_in_redis(
        r,
        pickup_nodes,
        delivery_nodes,
        robot_handler.name
    )

    print(f"Created request {request_uuid} for robot {robot_handler.name}")

    # Send pickup job
    pickup_job = {
        'operation': WarehouseOperation.PICKUP.value,
        'nodes': pickup_nodes
    }

    try:
        await robot_handler.send_job(pickup_job, request_uuid)
        print(f"Sent pickup job to {robot_handler.name}")

        # Queue delivery job (will execute after pickup completes)
        # Important: Must pass the same request_uuid so it can find the correct cell
        delivery_job = {
            'operation': WarehouseOperation.DELIVERY.value,
            'nodes': delivery_nodes,
            'request_uuid': request_uuid  # Store UUID in job for later use
        }
        robot_handler.job_queue.append(delivery_job)
        print(f"Queued delivery job for {robot_handler.name}")

    except RuntimeError as e:
        print(f"Failed to send job: {e}")
        # Update request status to FAILED
        await r.hset(f"request:{request_uuid}", 'request_status', str(RequestStatus.FAILED.value))
        await r.publish(f"request:{request_uuid}:update", "updated")


async def send_travel_job(robot_handler: RobotHandler, waypoint_nodes: list[dict]):
    """
    Send a simple travel job to a robot.

    Args:
        robot_handler: Robot handler instance
        waypoint_nodes: List of waypoint nodes to travel through
    """
    travel_job = {
        'operation': WarehouseOperation.TRAVEL.value,
        'nodes': waypoint_nodes
    }

    try:
        await robot_handler.send_job(travel_job)
        print(f"Sent travel job to {robot_handler.name}")
    except RuntimeError as e:
        print(f"Failed to send travel job: {e}")


# Example usage
async def main():
    # Connect to Redis
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)

    # Create a robot handler (normally this would be done in main.py)
    robot = RobotHandler(
        name='Lertvilai',
        host_ip='192.168.123.171',
        port=8002,
        cell_heights=[0.5, 1.0, 1.5],
        redis_client=r
    )
    await robot.initialize_in_redis()

    # Example: Send travel job
    waypoints = [
        {'id': 1, 'x': 0.0, 'y': 0.0, 'node_type': 0},
        {'id': 2, 'x': 1.0, 'y': 1.0, 'node_type': 0},
        {'id': 3, 'x': 2.0, 'y': 2.0, 'node_type': 0}
    ]
    await send_travel_job(robot, waypoints)

    # Example: Send pickup and delivery request
    pickup_nodes = [
        {'id': 10, 'x': 0.0, 'y': 0.0, 'node_type': 0},  # Start waypoint
        {'id': 20, 'x': 5.0, 'y': 5.0, 'height': 1.0, 'node_type': 2}  # Shelf
    ]

    delivery_nodes = [
        {'id': 30, 'x': 2.0, 'y': 2.0, 'node_type': 0},  # Waypoint
        {'id': 40, 'x': 10.0, 'y': 10.0, 'node_type': 4}  # Depot
    ]

    await send_pickup_delivery_request(robot, r, pickup_nodes, delivery_nodes)

    # Keep running to process callbacks
    await asyncio.sleep(60)

    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
