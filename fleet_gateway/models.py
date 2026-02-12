"""
Shared data models for the fleet gateway system.

These are plain Python dataclasses that can be used across the system.
GraphQL schema wraps these with @strawberry.type for API exposure.
"""

from dataclasses import dataclass
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
    operation: WarehouseOperation
    nodes: list[Node]


@dataclass
class Robot:
    """Robot state"""
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
