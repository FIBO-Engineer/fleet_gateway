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
from fleet_gateway.robot import RobotConnector
from fleet_gateway.job_store import JobStore
from fleet_gateway.api.types import Job, Node
from fleet_gateway.enums import JobOperation, OrderStatus, NodeType


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
        'operation': JobOperation.PICKUP.value,
        'nodes': pickup_nodes
    }

    delivery_job = {
        'operation': JobOperation.DELIVERY.value,
        'nodes': delivery_nodes
    }

    request_data = {
        'uuid': request_uuid,
        'pickup': json.dumps(pickup_job),
        'delivery': json.dumps(delivery_job),
        'handler': handler_name,
        'request_status': str(OrderStatus.IN_PROGRESS.value)
    }

    await r.hset(f"request:{request_uuid}", mapping=request_data)
    await r.publish(f"request:{request_uuid}:update", "updated")

    return request_uuid


async def send_pickup_delivery_request(
    robot_handler: RobotConnector,
    r: redis.Redis,
    pickup_nodes: list[dict],
    delivery_nodes: list[dict]
):
    """
    Send a complete pickup and delivery request to a robot.

    NOTE: This example manually manages cell allocation. In production,
    use FleetOrchestrator which handles this automatically.

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

    # Manually track cell holdings (normally done by FleetOrchestrator)
    cell_holdings: list[str | None] = [None] * len(robot_handler.state.robot_cell_heights)

    try:
        # Find free cell for pickup
        shelf_height = pickup_nodes[-1].get('height', 0.0)
        target_cell = robot_handler.find_free_cell(shelf_height)
        if target_cell == -1:
            raise RuntimeError("No free cell available for pickup")

        # Generate job UUIDs for tracking
        pickup_job_uuid = str(uuid4())
        delivery_job_uuid = str(uuid4())

        # Convert node dicts to Node objects
        pickup_node_objs = [
            Node(
                id=n['id'],
                alias=n.get('alias'),
                x=n['x'],
                y=n['y'],
                height=n.get('height'),
                node_type=NodeType(n['node_type'])
            )
            for n in pickup_nodes
        ]
        delivery_node_objs = [
            Node(
                id=n['id'],
                alias=n.get('alias'),
                x=n['x'],
                y=n['y'],
                height=n.get('height'),
                node_type=NodeType(n['node_type'])
            )
            for n in delivery_nodes
        ]

        # Create pickup job
        pickup_job = Job(
            uuid=pickup_job_uuid,
            operation=JobOperation.PICKUP,
            nodes=pickup_node_objs,
            robot_cell=target_cell,
            request_uuid=request_uuid
        )
        await robot_handler.send_job(pickup_job)
        print(f"Sent pickup job {pickup_job_uuid} to {robot_handler.name} (cell {target_cell})")

        # Update local tracking
        cell_holdings[target_cell] = request_uuid

        # Create and queue delivery job (store UUID only)
        delivery_job = Job(
            uuid=delivery_job_uuid,
            operation=JobOperation.DELIVERY,
            nodes=delivery_node_objs,
            robot_cell=target_cell,
            request_uuid=request_uuid
        )
        # Persist job to Redis using JobStore
        job_store = JobStore(r)
        await job_store.upsert_job(delivery_job)
        # Store full Job object in state
        robot_handler.state.jobs.append(delivery_job)
        print(f"Queued delivery job {delivery_job_uuid} for {robot_handler.name} (cell {target_cell})")

    except RuntimeError as e:
        print(f"Failed to send job: {e}")
        # Update request status to FAILED
        await r.hset(f"request:{request_uuid}", 'request_status', str(OrderStatus.FAILED.value))
        await r.publish(f"request:{request_uuid}:update", "updated")


async def send_travel_job(robot_handler: RobotConnector, waypoint_nodes: list[dict]):
    """
    Send a simple travel job to a robot.

    Args:
        robot_handler: Robot handler instance
        waypoint_nodes: List of waypoint nodes to travel through
    """
    # Generate job UUID for tracking
    job_uuid = str(uuid4())

    travel_job = {
        'uuid': job_uuid,
        'operation': JobOperation.TRAVEL.value,
        'nodes': waypoint_nodes,
        'target_cell': -1  # No cell needed for TRAVEL
    }

    try:
        await robot_handler.send_job(travel_job)
        print(f"Sent travel job {job_uuid} to {robot_handler.name}")
    except RuntimeError as e:
        print(f"Failed to send travel job: {e}")


# Example usage
async def main():
    # Connect to Redis
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)

    # Create a robot handler (normally this would be done in main.py)
    robot = RobotConnector(
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
