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
import fleet_gateway.api.type_resolvers as resolvers

# For type checking, use the plain enums
# At runtime, use the Strawberry-wrapped versions
if TYPE_CHECKING:
    from fleet_gateway.enums import NodeType, RobotStatus, JobOperation, RequestStatus
else:
    NodeType = strawberry.enum(enums.NodeType)
    RobotStatus = strawberry.enum(enums.RobotStatus)
    JobOperation = strawberry.enum(enums.JobOperation)
    RequestStatus = strawberry.enum(enums.RequestStatus)

# Note: In redis, it'll store ID for fast query

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
    estimated_tag: Node | None = None 
    x: float | None = None
    y: float | None = None
    a: float | None = None

@strawberry.type
class PiggybackState:
    """Piggyback manipulator state"""
    axis_0: float | None = None
    axis_1: float | None = None
    axis_2: float | None = None
    gripper: bool | None = None

@strawberry.type
class Request:
    """Warehouse request (pickup + delivery pair)"""
    uuid: UUID
    status: RequestStatus
    pickup: Job = strawberry.field(resolver=resolvers.get_pickup_job_by_request)
    delivery: Job = strawberry.field(resolver=resolvers.get_delievery_job_by_request)
    handling_robot: Robot | None = strawberry.field(resolver=resolvers.get_handling_robot_by_request)

@strawberry.type
class Job:
    """Robot job with operation type and path nodes"""
    """Path resolved at job time"""
    uuid: UUID
    operation: JobOperation
    target_node: Node | None = strawberry.field(resolver=resolvers.get_target_node_by_job)
    request: Request | None = strawberry.field(resolver=resolvers.get_request_by_job)
    handling_robot: Robot = strawberry.field(resolver=resolvers.get_handling_robot_by_job)

@strawberry.type
class Robot:
    """Robot state and configuration"""
    name: str
    status: RobotStatus
    mobile_base_status: MobileBaseState
    piggyback_state: PiggybackState

    # Cell allocations: request UUID per cell (None = empty cell)
    cells: list[RobotCell] = strawberry.field(resolver=resolvers.get_robot_cells_by_robot)
    current_job: Job | None = strawberry.field(resolver=resolvers.get_current_job_by_robot)
    job_queue: list[Job] = strawberry.field(resolver=resolvers.get_job_queue_by_robot)

    
@strawberry.type
class RobotCell:
    """Robot job with operation type and path nodes"""
    robot: Robot = strawberry.field(resolver=resolvers.get_robot_by_robot_cell)
    height: float
    holding: Request | None = strawberry.field(resolver=resolvers.get_holding_by_robot_cell)

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
    request: list[Request]
    # message: str