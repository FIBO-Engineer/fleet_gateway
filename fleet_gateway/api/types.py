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
    height: float
    node_type: NodeType

@strawberry.type
class Request:
    """Warehouse request (pickup + delivery pair)"""
    uuid: UUID
    status: RequestStatus
    pickup: Job = strawberry.field(resolver=resolvers.get_pickup_job_by_request)
    delivery: Job = strawberry.field(resolver=resolvers.get_delievery_job_by_request)
    handling_robot: Robot = strawberry.field(resolver=resolvers.get_handling_robot_by_request)
    # Private variables
    _pickup_uuid: strawberry.Private[UUID]
    _delivery_uuid: strawberry.Private[UUID]
    _handling_robot_name: strawberry.Private[str]

@strawberry.type
class Job:
    """Robot job with operation type and path nodes"""
    """Path resolved at job time"""
    uuid: UUID
    operation: JobOperation
    target_node: Node
    request: Request | None = strawberry.field(resolver=resolvers.get_request_by_job, default=None)
    handling_robot: Robot = strawberry.field(resolver=resolvers.get_handling_robot_by_job)
    # Private variables
    _request_uuid: strawberry.Private[UUID | None] = None
    _handling_robot_name: strawberry.Private[str]

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
    lift: float | None = None
    turntable: float | None = None
    insert: float | None = None
    hook: bool | None = None

@strawberry.type
class Robot:
    """Robot state and configuration"""
    name: str
    status: RobotStatus
    mobile_base_state: MobileBaseState
    piggyback_state: PiggybackState

    # Cell allocations: request UUID per cell (None = empty cell)
    cells: list[RobotCell] = strawberry.field(resolver=resolvers.get_robot_cells_by_robot)
    current_job: Job | None = strawberry.field(resolver=resolvers.get_current_job_by_robot, default=None)
    job_queue: list[Job] = strawberry.field(resolver=resolvers.get_job_queue_by_robot)
    # Private variables
    _current_job_uuid: strawberry.Private[UUID | None] = None
    _job_queue_uuid: strawberry.Private[list[UUID]] = strawberry.field(default_factory=list)

    
@strawberry.type
class RobotCell:
    """Robot cell storage with height and holding capacity"""
    height: float
    holding: Request | None = strawberry.field(resolver=resolvers.get_holding_by_robot_cell, default=None)
    # Private variables
    _holding_uuid: strawberry.Private[str | None] = None

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