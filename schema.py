import strawberry
from uuid import UUID
from enum import Enum
import redis.asyncio as redis

@strawberry.enum
class NodeType(Enum):
    WAYPOINT = 0
    CONVEYOR = 1
    SHELF = 2
    CELL = 3
    DEPOT = 4

@strawberry.enum
class RobotStatus(Enum):
    OFFLINE = 0
    IDLE = 1
    INACTIVE = 2
    BUSY = 3

@strawberry.type
class Node:
    id: int
    alias: str | None
    x: float
    y: float
    height: float | None
    node_type: NodeType

@strawberry.type
class MobileBaseState:
    last_seen: Node
    x: float
    y: float
    a: float

@strawberry.type
class PiggybackState:
    axis_0: float
    axis_1: float
    axis_2: float
    gripper: bool

@strawberry.enum
class WarehouseOperation(Enum):
    TRAVEL = 0
    PICKUP = 1
    DELIVERY = 2

@strawberry.type
class Job:
    operation: WarehouseOperation
    nodes: list[Node]

@strawberry.type
class Request:
    uuid: UUID
    pickup: Job
    delivery: Job
    handler: Robot
    request_status: RequestStatus

@strawberry.type
class Robot:
    name: str
    robot_cell_heights: list[float]

    robot_status: RobotStatus 
    mobile_base_status: MobileBaseState
    piggyback_state: PiggybackState
    holdings: list[Request]

    current_job: Job
    jobs: list[Job]

    
@strawberry.enum
class RequestStatus(Enum):
    CANCELLED = 0
    FAILED = 1
    IN_PROGRESS = 2
    COMPLETED = 3

@strawberry.type
class Query:
    @strawberry.field
    async def robots(self, info: strawberry.types.Info) -> list[Robot]:
        r: redis.Redis = info.context["redis"]

    @strawberry.field
    async def requests(self, info: strawberry.types.Info) -> list[Request]:
        r: redis.Redis = info.context["redis"]

    @strawberry.field
    async def robot(self, info: strawberry.types.Info, name: str) -> Robot:
        r: redis.Redis = info.context["redis"]
        data = await r.hgetall(f"robot:{name}")

    @strawberry.field
    async def request(self, info: strawberry.types.Info, uuid: UUID) -> Request:
        r: redis.Redis = info.context["redis"]
