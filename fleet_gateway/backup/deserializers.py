"""
Deserializers for converting Redis data to GraphQL types.

These functions convert JSON-serialized data from Redis hashes
back into typed Python objects for GraphQL responses.
"""

import json
from uuid import UUID

from fleet_gateway.enums import NodeType, RobotStatus, JobOperation, OrderStatus
from ..api.types import Node, MobileBaseState, PiggybackState, Job, Robot, Request


def deserialize_node(data: dict) -> Node:
    """Convert Redis node data to Node type"""
    return Node(
        id=int(data['id']),
        alias=data.get('alias'),
        x=float(data['x']),
        y=float(data['y']),
        height=float(data['height']) if data.get('height') else None,
        node_type=NodeType(int(data['node_type']))
    )


def deserialize_mobile_base_state(data: dict) -> MobileBaseState:
    """Convert Redis mobile base state to MobileBaseState type"""
    return MobileBaseState(
        estimated_tag=deserialize_node(json.loads(data['last_seen'])),
        x=float(data['x']),
        y=float(data['y']),
        a=float(data['a'])
    )


def deserialize_piggyback_state(data: dict) -> PiggybackState:
    """Convert Redis piggyback state to PiggybackState type"""
    return PiggybackState(
        lift=float(data['lift']),
        turntable=float(data['turntable']),
        insert=float(data['insert']),
        hook=data['hook'].lower() == 'true'
    )


def deserialize_job(data: dict) -> Job:
    """Convert Redis job data to Job type"""
    return Job(
        uuid=data['uuid'],
        operation=JobOperation(int(data['operation'])),
        nodes=[
            Node(
                id=int(n['id']),
                alias=n.get('alias'),
                x=float(n['x']),
                y=float(n['y']),
                height=float(n['height']) if n.get('height') is not None else None,
                node_type=NodeType(int(n['node_type']))
            )
            for n in json.loads(data['nodes'])
        ],
        robot_cell=int(data.get('target_cell', -1)),
        request_uuid=data.get('request_uuid') or None
    )


def deserialize_robot(data: dict) -> Robot:
    """Convert Redis robot data to Robot type

    Note: current_job and jobs are now stored as UUIDs in Redis.
    These need to be fetched separately via deserialize_robot_with_jobs()
    """
    return Robot(
        name=data['name'],
        robot_cell_heights=[float(h) for h in json.loads(data['robot_cell_heights'])],
        status=RobotStatus(int(data['robot_status'])),
        mobile_base_state=deserialize_mobile_base_state(json.loads(data['mobile_base_state'])),
        piggyback_state=deserialize_piggyback_state(json.loads(data['piggyback_state'])),
        holdings=json.loads(data.get('cell_holdings', '[]')),
        holdings=[],  # Will be populated separately if needed
        current_job=None,  # Will be populated by deserialize_robot_with_jobs() if needed
        jobs=[]  # Will be populated by deserialize_robot_with_jobs() if needed
    )


def deserialize_request(data: dict, robot_lookup: dict[str, Robot]) -> Request:
    """Convert Redis request data to Request type"""
    return Request(
        uuid=UUID(data['uuid']),
        pickup=deserialize_job(json.loads(data['pickup'])),
        delivery=deserialize_job(json.loads(data['delivery'])),
        handling_robot=robot_lookup.get(data['handler']),
        status=OrderStatus(int(data['request_status']))
    )


async def deserialize_robot_with_jobs(data: dict, redis_client) -> Robot:
    """
    Convert Redis robot data to Robot type with jobs fetched from Redis.

    Args:
        data: Robot data from Redis
        redis_client: Redis connection to fetch job details

    Returns:
        Robot with current_job and jobs populated
    """
    import redis.asyncio as redis

    robot = deserialize_robot(data)

    # Fetch current_job if it exists (stored as UUID string)
    current_job_uuid = data.get('current_job')
    if current_job_uuid:
        job_data = await redis_client.hgetall(f"job:{current_job_uuid}")
        if job_data:
            # Convert bytes to strings
            job_dict = {k.decode() if isinstance(k, bytes) else k:
                       v.decode() if isinstance(v, bytes) else v
                       for k, v in job_data.items()}
            robot.current_job = deserialize_job(job_dict)

    # Fetch queued jobs (stored as JSON array of UUIDs)
    jobs_uuids = json.loads(data.get('jobs', '[]'))
    for job_uuid in jobs_uuids:
        job_data = await redis_client.hgetall(f"job:{job_uuid}")
        if job_data:
            # Convert bytes to strings
            job_dict = {k.decode() if isinstance(k, bytes) else k:
                       v.decode() if isinstance(v, bytes) else v
                       for k, v in job_data.items()}
            robot.jobs.append(deserialize_job(job_dict))

    return robot
