"""
Job and Request serialization helpers for Redis persistence.

Converts Job and Request objects to/from Redis hash format.
"""

from __future__ import annotations

from fleet_gateway.enums import NodeType, WarehouseOperation
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
        'robot_cell': job.robot_cell,
        'request': job.request. or ''
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
        robot_cell=int(data.get('robot_cell', -1)),
        request_uuid=data.get('request_uuid') or None
    )


def request_to_dict(request: Request) -> dict:
    """Convert Request object to dict for Redis storage"""
    return {
        'uuid': str(request.uuid),
        'pickup': request.pickup.uuid,
        'delivery': request.delivery.uuid,
        'handler': request.handling_robot.name if request.handling_robot else '',
        'request_status': request.status.value
    }


