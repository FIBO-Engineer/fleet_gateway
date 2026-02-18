"""
Job and Request deserialization helpers for Redis persistence.

Converts Redis hash format back to Job and Request objects.
"""

import json
from uuid import UUID

from fleet_gateway.enums import NodeType, JobOperation, RequestStatus
from fleet_gateway.api.types import Node, Request, Job


def dict_to_node(data: dict) -> Node:
    """Convert dict to Node object"""
    return Node(
        id=int(data['id']),
        alias=data['alias'],
        x=float(data['x']),
        y=float(data['y']),
        height=float(data['height']),
        node_type=NodeType(int(data['node_type']))
    )


def dict_to_request(data: dict) -> Request:
    """Convert dict from Redis storage to Request object"""
    return Request(
        uuid=UUID(data['uuid']),
        status=RequestStatus(int(data['status'])),
        _pickup_uuid=UUID(data['pickup']),
        _delivery_uuid=UUID(data['delivery']),
        _handling_robot_name=data['handling_robot']
    )


def dict_to_job(data: dict) -> Job:
    """Convert dict from Redis storage to Job object"""
    # Parse target_node if it's a dict, otherwise assume it's already parsed
    return Job(
        uuid=UUID(data['uuid']),
        operation=JobOperation(int(data['operation'])),
        target_node=dict_to_node(json.loads(data['target_node'])),
        _request_uuid=UUID(data['request']) if data.get('request') else None,
        _handling_robot_name=data['handling_robot']
    )