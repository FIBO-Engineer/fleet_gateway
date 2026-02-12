"""
Job serialization helpers for Redis persistence.

Converts Job objects to/from Redis hash format.
"""

from __future__ import annotations

from fleet_gateway.enums import NodeType, WarehouseOperation
from fleet_gateway.api.types import Job, Node


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
