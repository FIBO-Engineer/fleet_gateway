"""
GraphQL type definitions for Fleet Gateway API.

These @strawberry.type classes mirror the dataclasses in models.py.
The dataclasses are used internally, while these are exposed via GraphQL.
"""
from __future__ import annotations
import strawberry
from uuid import UUID
from datetime import datetime

from fleet_gateway import enums
import fleet_gateway.api.type_resolvers as resolvers

NodeType = strawberry.enum(enums.NodeType)
RobotConnectionStatus = strawberry.enum(enums.RobotConnectionStatus)
RobotActionStatus = strawberry.enum(enums.RobotActionStatus)
JobOperation = strawberry.enum(enums.JobOperation)
OrderStatus = strawberry.enum(enums.OrderStatus)

# Note: In redis, it'll store ID for fast query

@strawberry.type
class Node:
    """Warehouse path network node"""
    id: int
    alias: str | None
    tag_id: str | None
    x: float
    y: float
    height: float
    node_type: NodeType

@strawberry.type
class Request:
    """Warehouse request (pickup + delivery pair)"""
    uuid: UUID
    status: OrderStatus = strawberry.field(resolver=resolvers.get_request_status)
    pickup: Job = strawberry.field(resolver=resolvers.get_pickup_job_by_request)
    delivery: Job = strawberry.field(resolver=resolvers.get_delievery_job_by_request)
    handling_robot: Robot = strawberry.field(resolver=resolvers.get_handling_robot_by_request)
    # Private variables
    pickup_uuid: strawberry.Private[UUID]
    delivery_uuid: strawberry.Private[UUID]
    handling_robot_name: strawberry.Private[str]

@strawberry.type
class Job:
    """Robot job with operation type and path nodes"""
    """Path resolved at job time"""
    uuid: UUID
    status: OrderStatus
    operation: JobOperation
    target_node: Node
    request: Request | None = strawberry.field(resolver=resolvers.get_request_by_job)
    handling_robot: Robot = strawberry.field(resolver=resolvers.get_handling_robot_by_job)
    # Private variables
    request_uuid: strawberry.Private[UUID | None]
    handling_robot_name: strawberry.Private[str]

@strawberry.type
class Tag:
    timestamp: datetime
    qr_id: str

@strawberry.type
class Pose:
    timestamp: datetime
    x: float
    y: float
    a: float

@strawberry.type
class MobileBaseState:
    """Mobile base position and orientation"""
    tag: Tag | None
    pose: Pose | None

@strawberry.type
class PiggybackState:
    """Piggyback manipulator state"""
    timestamp: datetime
    lift: float
    turntable: float
    slide: float
    hook_left: float
    hook_right: float

@strawberry.type
class Robot:
    """Robot state and configuration"""
    name: str
    connection_status: RobotConnectionStatus
    last_action_status: RobotActionStatus
    mobile_base_state: MobileBaseState | None
    piggyback_state: PiggybackState | None

    # Cell allocations: request UUID per cell (None = empty cell)
    cells: list[RobotCell] = strawberry.field(resolver=resolvers.get_robot_cells_by_robot)
    current_job: Job | None = strawberry.field(resolver=resolvers.get_current_job_by_robot)
    job_queue: list[Job] = strawberry.field(resolver=resolvers.get_job_queue_by_robot)
    # Private variables
    current_job_uuid: strawberry.Private[UUID | None] = None
    job_queue_uuid: strawberry.Private[list[UUID]] = strawberry.field(default_factory=list)

    
@strawberry.type
class RobotCell:
    """Robot cell storage with height and holding capacity"""
    height: float
    holding: Job | None = strawberry.field(resolver=resolvers.get_holding_by_robot_cell)
    # Private variables
    holding_uuid: strawberry.Private[UUID | None]

# Helper types
@strawberry.input
class RequestInput:
    """Input for a warehouse request (pickup + delivery pair)"""
    pickup_node_id: int  # Node ID of the shelf to pick from
    delivery_node_id: int  # Node ID of the depot to deliver to

@strawberry.input
class AssignmentInput:
    """Input for a robot assignment"""
    robot_name: str  # Name of the robot
    route_node_ids: list[int]  # List of node IDs to visit in order

# Input types for mutations
@strawberry.input
class JobOrderInput:
    robot_name: str
    target_node_id: int
    operation: JobOperation

@strawberry.input
class RequestOrderInput:
    robot_name: str
    request: RequestInput

@strawberry.input
class WarehouseOrderInput:
    requests: list[RequestInput]
    assignments: list[AssignmentInput]

@strawberry.input
class RobotCellInput:
    robot_name: str
    cell_index: int

# Mutation Result Types
@strawberry.type
class JobOrderResult:
    success: bool
    message: str
    job: Job | None
    
@strawberry.type
class RequestOrderResult:
    success: bool
    message: str
    request: Request | None

@strawberry.type
class WarehouseOrderResult:
    """Result of submitting requests and assignments"""
    success: bool
    message: str
    requests: list[Request]