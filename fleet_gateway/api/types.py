"""
GraphQL type definitions for Fleet Gateway API.

These @strawberry.type classes mirror the dataclasses in models.py.
The dataclasses are used internally, while these are exposed via GraphQL.
"""

import strawberry
from uuid import UUID
from typing import TYPE_CHECKING
from fleet_gateway import request_store

from fleet_gateway import enums
import fleet_gateway.api.resolvers as resolvers

# For type checking, use the plain enums
# At runtime, use the Strawberry-wrapped versions
if TYPE_CHECKING:
    from fleet_gateway.enums import NodeType, RobotStatus, WarehouseOperation, RequestStatus
else:
    NodeType = strawberry.enum(enums.NodeType)
    RobotStatus = strawberry.enum(enums.RobotStatus)
    WarehouseOperation = strawberry.enum(enums.WarehouseOperation)
    RequestStatus = strawberry.enum(enums.RequestStatus)


@strawberry.type
class Node:
    """Warehouse path network node"""
    id: int
    alias: str | None
    x: float
    y: float
    height: float | None
    node_type: NodeType


@strawberry.type
class MobileBaseState:
    """Mobile base position and orientation"""
    last_seen: Node | None 
    x: float
    y: float
    a: float


@strawberry.type
class PiggybackState:
    """Piggyback manipulator state"""
    axis_0: float
    axis_1: float
    axis_2: float
    gripper: bool


@strawberry.type
class Job:
    """Robot job with operation type and path nodes"""
    uuid: UUID
    operation: WarehouseOperation
    nodes: list[Node]
    robot_cell: int
    request: Request | None = strawberry.field(resolver=resolvers.get_request_by_job)

@strawberry.type
class Robot:
    """Robot state and configuration"""
    name: str
    robot_cell_heights: list[float]

    status: RobotStatus
    mobile_base_status: MobileBaseState
    piggyback_state: PiggybackState

    # Cell allocations: request UUID per cell (None = empty cell)
    holdings: list[Request | None] = strawberry.field(resolver=resolvers.get_holdings_by_robot)

    current_job: Job | None = strawberry.field(resolver=resolvers.get_current_job_by_robot)
    job_queue: list[Job] = strawberry.field(resolver=resolvers.get_job_queue_by_robot)


@strawberry.type
class Request:
    """Warehouse request (pickup + delivery pair)"""
    uuid: UUID
    pickup: Job = strawberry.field(resolver=resolvers.get_pickup_job_by_request)
    delivery: Job = strawberry.field(resolver=resolvers.get_delievery_job_by_request)
    handling_robot: Robot | None = strawberry.field(resolver=resolvers.get_handling_robot_by_request)
    status: RequestStatus

# Input types for mutations
@strawberry.input
class RequestInput:
    """Input for a warehouse request (pickup + delivery pair)"""
    pickup_id: int  # Node ID of the shelf to pick from
    delivery_id: int  # Node ID of the depot to deliver to


@strawberry.input
class AssignmentInput:
    """Input for a robot assignment"""
    robot_name: str  # Name of the robot
    route_node_ids: list[int]  # List of node IDs to visit in order
    
@strawberry.type
class OrderResult:
    """Result of submitting requests and assignments"""
    success: bool
    request: list[Request] = strawberry.field(resolver=resolvers.get_new_requests)
    # message: str