"""
Deserializers for converting Redis data to GraphQL types.

These functions convert JSON-serialized data from Redis hashes
back into typed Python objects for GraphQL responses.
"""

import json
from uuid import UUID

from fleet_gateway.enums import NodeType, RobotStatus, WarehouseOperation, RequestStatus
from .types import Node, MobileBaseState, PiggybackState, Job, Robot, Request


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
        last_seen=deserialize_node(json.loads(data['last_seen'])),
        x=float(data['x']),
        y=float(data['y']),
        a=float(data['a'])
    )


def deserialize_piggyback_state(data: dict) -> PiggybackState:
    """Convert Redis piggyback state to PiggybackState type"""
    return PiggybackState(
        axis_0=float(data['axis_0']),
        axis_1=float(data['axis_1']),
        axis_2=float(data['axis_2']),
        gripper=data['gripper'].lower() == 'true'
    )


def deserialize_job(data: dict) -> Job:
    """Convert Redis job data to Job type"""
    return Job(
        operation=WarehouseOperation(int(data['operation'])),
        nodes=[deserialize_node(n) for n in json.loads(data['nodes'])]
    )


def deserialize_robot(data: dict) -> Robot:
    """Convert Redis robot data to Robot type"""
    return Robot(
        name=data['name'],
        robot_cell_heights=[float(h) for h in json.loads(data['robot_cell_heights'])],
        robot_status=RobotStatus(int(data['robot_status'])),
        mobile_base_status=deserialize_mobile_base_state(json.loads(data['mobile_base_status'])),
        piggyback_state=deserialize_piggyback_state(json.loads(data['piggyback_state'])),
        holdings=[],  # Will be populated separately if needed
        current_job=deserialize_job(json.loads(data['current_job'])) if data.get('current_job') else None,
        jobs=[deserialize_job(j) for j in json.loads(data['jobs'])] if data.get('jobs') else []
    )


def deserialize_request(data: dict, robot_lookup: dict[str, Robot]) -> Request:
    """Convert Redis request data to Request type"""
    return Request(
        uuid=UUID(data['uuid']),
        pickup=deserialize_job(json.loads(data['pickup'])),
        delivery=deserialize_job(json.loads(data['delivery'])),
        handler=robot_lookup.get(data['handler']),
        request_status=RequestStatus(int(data['request_status']))
    )
