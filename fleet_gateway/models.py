"""
Shared data models for the fleet gateway system.

These are plain Python dataclasses that can be used across the system.
GraphQL schema wraps these with @strawberry.type for API exposure.
"""

from dataclasses import dataclass, field
from uuid import UUID

from fleet_gateway.enums import NodeType, RobotStatus, WarehouseOperation, RequestStatus


@dataclass
class Node:
    """Node in the warehouse path network"""
    id: int
    alias: str | None
    x: float
    y: float
    height: float | None
    node_type: NodeType


@dataclass
class MobileBaseState:
    """Mobile base state (position and orientation)"""
    last_seen: Node
    x: float
    y: float
    a: float  # Angle/orientation


@dataclass
class PiggybackState:
    """Piggyback manipulator state"""
    axis_0: float
    axis_1: float
    axis_2: float
    gripper: bool


@dataclass
class Job:
    """A job for a robot (movement with operation type)"""
    uuid: str  # Job tracking UUID (mandatory for Redis lookups)
    operation: WarehouseOperation
    nodes: list[Node]
    target_cell: int = -1  # Cell index for PICKUP/DELIVERY, -1 for TRAVEL


@dataclass
class RobotState:
    """
    Internal robot state used by RobotHandler.

    Jobs are now typed Job objects for type safety.
    Converted to/from dicts only at Redis serialization boundaries.
    """
    name: str
    robot_cell_heights: list[float]
    robot_status: RobotStatus = RobotStatus.OFFLINE
    mobile_base_status: MobileBaseState = field(default_factory=lambda: MobileBaseState(
        last_seen=Node(id=0, alias=None, x=0.0, y=0.0, height=0.0, node_type=NodeType.WAYPOINT),
        x=0.0,
        y=0.0,
        a=0.0
    ))
    piggyback_state: PiggybackState = field(default_factory=lambda: PiggybackState(
        axis_0=0.0,
        axis_1=0.0,
        axis_2=0.0,
        gripper=False
    ))
    current_job: Job | None = None
    jobs: list[Job] = field(default_factory=list)


@dataclass
class Robot:
    """Robot state for GraphQL API"""
    name: str
    robot_cell_heights: list[float]
    robot_status: RobotStatus
    mobile_base_status: MobileBaseState
    piggyback_state: PiggybackState
    holdings: list['Request']
    current_job: Job | None
    jobs: list[Job]


@dataclass
class Request:
    """Warehouse request (pickup + delivery pair)"""
    uuid: UUID
    pickup: Job
    delivery: Job
    handler: Robot | None
    request_status: RequestStatus


# === Job Serialization Helpers ===

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
        'target_cell': job.target_cell
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
        target_cell=int(data.get('target_cell', -1))
    )
