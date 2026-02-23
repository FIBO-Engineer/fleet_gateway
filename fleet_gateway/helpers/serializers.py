"""
Job and Request serialization helpers for Redis persistence.

Converts Job and Request objects to/from Redis hash format.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import json

if TYPE_CHECKING:
    from fleet_gateway.api.types import Node, Request, Job

def node_to_dict(node: Node) -> dict:
    """Convert Node object to dict"""
    return {
        'id': node.id,
        'alias': node.alias,
        'tag_id': node.tag_id,
        'x': node.x,
        'y': node.y,
        'height': node.height,
        'node_type': node.node_type.value
    }

def request_to_dict(request: Request) -> dict:
    """Convert Request object to dict for Redis storage"""
    return {
        # 'uuid': str(request.uuid),
        'pickup': str(request.pickup_uuid),
        'delivery': str(request.delivery_uuid),
        'handling_robot': request.handling_robot_name,
    }

def job_to_dict(job: Job) -> dict:
    """Convert Job object to dict for Redis storage"""
    return {
        # 'uuid': str(job.uuid),
        'status': job.status.value,
        'operation': job.operation.value,
        'target_node': json.dumps(node_to_dict(job.target_node)),
        'request': str(job.request_uuid) if job.request_uuid else "",
        'handling_robot': job.handling_robot_name
    }

# Not really needed yet, store as variable

# def mobile_base_state_to_dict(mobile_base_state: MobileBaseState) -> dict:
#     """Convert Mobile Base state"""
#     return {
#         'estimated_tag': node_to_dict(mobile_base_state.estimated_tag) if mobile_base_state.estimated_tag else {},
#         'x': mobile_base_state.x,
#         'y': mobile_base_state.y,
#         'a': mobile_base_state.a
#     }

# def piggyback_state_to_dict(piggyback_state: PiggybackState) -> dict:
#     """Convert Piggyback state"""
#     return {
#         'lift': piggyback_state.lift, 
#         'turntable': piggyback_state.turntable,
#         'insert': piggyback_state.insert,
#         'hook': piggyback_state.hook
#     }


# def robot_to_dict(robot: Robot) -> dict:
#     """Save robot state to Redis (jobs stored as UUIDs, full objects kept in memory)"""

#     mobile_base_dict = mobile_base_state_to_dict(robot.mobile_base_state)
#     piggyback_dict = piggyback_dict(robot.piggyback_state)

#     return {
#         'name': robot.name,
#         'status': robot.status.value,
#         'mobile_base_state': mobile_base_dict,
#         'piggyback_state': piggyback_dict,
#         'cells': json.dumps([robot_cell_to_dict(robot_cell) for robot_cell in robot.cells]),
#         'current_job': robot.current_job.uuid if robot.current_job else '',
#         'job_queue': json.dumps([job.uuid for job in robot.job_queue]),
#     }

# def robot_cell_to_dict(robot_cell: RobotCell) -> dict:
#     """Convert RobotCell object to dict"""
#     return {
#         'robot': robot_cell.robot.name,
#         'height': robot_cell.height,
#         'holding': robot_cell.holding.uuid if robot_cell.holding else ''
#     }







