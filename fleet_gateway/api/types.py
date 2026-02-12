"""
GraphQL type definitions for Fleet Gateway API.

These @strawberry.type classes mirror the dataclasses in models.py.
The dataclasses are used internally, while these are exposed via GraphQL.
"""

import strawberry
from uuid import UUID
from typing import TYPE_CHECKING

from fleet_gateway import enums

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
    target_cell: int
    request_uuid: UUID | None

    @strawberry.field
    async def request(self, info: strawberry.types.Info) -> "Request | None":
        """
        Resolve request_uuid to full Request object.
        Only fetches when client queries job.request
        """
        if not self.request_uuid:
            return None

        # Get Redis from context
        import redis.asyncio as redis
        from uuid import UUID
        from .data_loaders import load_request

        r: redis.Redis = info.context["redis"]
        return await load_request(r, UUID(self.request_uuid))


@strawberry.type
class Robot:
    """Robot state and configuration"""
    name: str
    robot_cell_heights: list[float]

    robot_status: RobotStatus
    mobile_base_status: MobileBaseState
    piggyback_state: PiggybackState

    # Cell allocations: request UUID per cell (None = empty cell)
    cell_holdings: list[str | None]

    # Full Request objects for cells that have items
    holdings: list["Request"]

    current_job: Job | None
    jobs: list[Job]


@strawberry.type
class Request:
    """Warehouse request (pickup + delivery pair)"""
    uuid: UUID
    pickup: Job
    delivery: Job
    handler: Robot | None
    request_status: RequestStatus


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
class SubmitResult:
    """Result of submitting requests and assignments"""
    success: bool
    message: str
    request_uuids: list[str]  # UUIDs of created requests
