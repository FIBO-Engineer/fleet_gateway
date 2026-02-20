"""
Job and Request deserialization helpers for Redis persistence.

Converts Redis hash format back to Job and Request objects.
"""

import json
from uuid import UUID

from fleet_gateway.enums import NodeType, JobOperation, RequestStatus
from fleet_gateway.api.types import Node, Request, Job


def dict_to_node(data: dict) -> Node | None:
    """Convert dict to Node object"""
    return Node(
        id=int(data['id']),
        alias=data['alias'],
        tag_id=data['tag_id'],
        x=float(data['x']),
        y=float(data['y']),
        height=float(data['height']),
        node_type=NodeType(int(data['node_type']))
    )


def dict_to_request(uuid: UUID, data: dict) -> Request | None:
    """Convert dict from Redis storage to Request object"""
    if not data:
        return None
    return Request(
        uuid=uuid,
        status=RequestStatus(int(data['status'])),
        pickup_uuid=UUID(data['pickup']),
        delivery_uuid=UUID(data['delivery']),
        handling_robot_name=data['handling_robot']
    )


def dict_to_job(uuid: UUID, data: dict) -> Job | None:
    """Convert dict from Redis storage to Job object"""
    # Parse target_node if it's a dict, otherwise assume it's already parsed
    if not data:
        return None
    return Job(
        uuid=uuid,
        operation=JobOperation(int(data['operation'])),
        target_node=dict_to_node(json.loads(data['target_node'])),
        request_uuid=UUID(data['request']) if data.get('request') else None,
        handling_robot_name=data['handling_robot']
    )