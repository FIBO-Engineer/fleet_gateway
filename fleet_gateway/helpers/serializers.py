"""
Job and Request serialization helpers for Redis persistence.

Converts Job and Request objects to/from Redis hash format.
"""

from __future__ import annotations

from uuid import UUID
from fleet_gateway.enums import NodeType, WarehouseOperation, RequestStatus
from fleet_gateway.api.types import Job, Node, Request


def job_to_dict(job: Job) -> dict:
    """Convert Job object to dict for Redis storage"""
    import json
    return {
        'uuid': job.uuid,
        'operation': job.operation.value,
        'nodes': json.dumps([
            {
                'id': n.id,
                'alias': n.alias,
                'x': n.x,
                'y': n.y,
                'height': n.height,
                'node_type': n.node_type.value
            }
            for n in job.nodes
        ]),
        'target_cell': job.target_cell,
        'request_uuid': job.request_uuid or ''
    }


def dict_to_job(data: dict) -> Job:
    """Convert dict from Redis to Job object"""
    return Job(
        uuid=data['uuid'],
        operation=WarehouseOperation(int(data['operation'])),
        nodes=[
            Node(
                id=int(n['id']),
                alias=n.get('alias'),
                x=float(n['x']),
                y=float(n['y']),
                height=float(n['height']) if n.get('height') is not None else None,
                node_type=NodeType(int(n['node_type']))
            )
            for n in data['nodes']
        ],
        target_cell=int(data.get('target_cell', -1)),
        request_uuid=data.get('request_uuid') or None
    )


def request_to_dict(request: Request) -> dict:
    """Convert Request object to dict for Redis storage"""
    import json
    return {
        'uuid': str(request.uuid),
        'pickup': request.pickup.uuid,
        'delivery': request.delivery.uuid,
        'handler': request.handler.name if request.handler else '',
        'request_status': request.request_status.value
    }


def dict_to_request(data: dict) -> Request:
    """Convert dict from Redis to Request object"""
    import json

    pickup_dict = json.loads(data['pickup'])
    delivery_dict = json.loads(data['delivery'])

    return Request(
        uuid=UUID(data['uuid']),
        pickup=dict_to_job(pickup_dict),
        delivery=dict_to_job(delivery_dict),
        handler=None,  # Handler is resolved separately via robot name
        request_status=RequestStatus(int(data['request_status']))
    )
