"""
GraphQL type definitions for Fleet Gateway API.

These @strawberry.type classes mirror the dataclasses in models.py.
The dataclasses are used internally, while these are exposed via GraphQL.
"""
from __future__ import annotations
import strawberry
from uuid import UUID
from datetime import datetime
from typing import TYPE_CHECKING

from fleet_gateway import enums

if TYPE_CHECKING:
    from fleet_gateway.order_store import OrderStore
    from fleet_gateway.fleet_handler import FleetHandler

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
    # Private variables
    pickup_uuid: strawberry.Private[UUID]
    delivery_uuid: strawberry.Private[UUID]
    handling_robot_name: strawberry.Private[str]

    @strawberry.field
    async def status(self, info: strawberry.types.Info) -> OrderStatus:
        order_store: OrderStore = info.context["order_store"]
        return await order_store.get_request_status(self)

    @strawberry.field
    async def pickup(self, info: strawberry.types.Info) -> Job:
        order_store: OrderStore = info.context["order_store"]
        job = await order_store.get_job(self.pickup_uuid)
        if job is None:
            raise ValueError(f"Pickup job {self.pickup_uuid} not found in order_store")
        return job

    @strawberry.field
    async def delivery(self, info: strawberry.types.Info) -> Job:
        order_store: OrderStore = info.context["order_store"]
        job = await order_store.get_job(self.delivery_uuid)
        if job is None:
            raise ValueError(f"Delivery job {self.delivery_uuid} not found in order_store")
        return job

    @strawberry.field
    async def handling_robot(self, info: strawberry.types.Info) -> Robot:
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        robot = fleet_handler.get_robot(self.handling_robot_name)
        if robot is None:
            raise ValueError(f"Robot '{self.handling_robot_name}' not found in fleet")
        return robot

@strawberry.type
class Job:
    """Robot job with operation type and path nodes"""
    """Path resolved at job time"""
    uuid: UUID
    status: OrderStatus
    operation: JobOperation
    target_node: Node
    # Private variables
    request_uuid: strawberry.Private[UUID | None]
    handling_robot_name: strawberry.Private[str]

    @strawberry.field
    async def request(self, info: strawberry.types.Info) -> Request | None:
        if self.request_uuid is None:
            return None
        order_store: OrderStore = info.context["order_store"]
        return await order_store.get_request(self.request_uuid)

    @strawberry.field
    async def handling_robot(self, info: strawberry.types.Info) -> Robot:
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        robot = fleet_handler.get_robot(self.handling_robot_name)
        if robot is None:
            raise ValueError(f"Robot '{self.handling_robot_name}' not found in fleet")
        return robot

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
    # Private variables
    current_job_uuid: strawberry.Private[UUID | None] = None
    job_queue_uuid: strawberry.Private[list[UUID]] = strawberry.field(default_factory=list)

    @strawberry.field
    async def cells(self, info: strawberry.types.Info) -> list[RobotCell]:
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        return fleet_handler.get_robot_cells(self.name)

    @strawberry.field
    async def current_job(self, info: strawberry.types.Info) -> Job | None:
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        return fleet_handler.get_current_job(self.name)

    @strawberry.field
    async def job_queue(self, info: strawberry.types.Info) -> list[Job]:
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        return fleet_handler.get_job_queue(self.name)

@strawberry.type
class RobotCell:
    """Robot cell storage with height and holding capacity"""
    height: float
    # Private variables
    holding_uuid: strawberry.Private[UUID | None] = None

    @strawberry.field
    async def holding(self, info: strawberry.types.Info) -> Job | None:
        if self.holding_uuid is None:
            return None
        order_store: OrderStore = info.context["order_store"]
        return await order_store.get_job(self.holding_uuid)

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
    operation: JobOperation
    target_node_id: int | None = None
    target_node_alias: str | None = None

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
