"""
GraphQL field resolvers for Fleet Gateway types.

Contains field resolvers called from types.py to resolve nested GraphQL fields.
"""
from __future__ import annotations

import strawberry
from typing import TYPE_CHECKING

from fleet_gateway.order_store import OrderStore
from fleet_gateway.fleet_handler import FleetHandler

from fleet_gateway.enums import OrderStatus

if TYPE_CHECKING:
    from fleet_gateway.api.types import Job, Robot, Request, RobotCell

# Field resolvers for Request type (called from types.py)
async def get_request_status(request: Request, info: strawberry.types.Info) -> OrderStatus:
    """Resolve request from pickup and delivery job status from Request."""
    order_store: OrderStore = info.context["order_store"]
    return await order_store.get_request_status(request)

async def get_pickup_job_by_request(request: Request, info: strawberry.types.Info) -> Job:
    """Resolve pickup Job from Request."""
    order_store: OrderStore = info.context["order_store"]
    return await order_store.get_job(request.pickup_uuid)


async def get_delievery_job_by_request(request: Request, info: strawberry.types.Info) -> Job:
    """Resolve delivery Job from Request."""
    order_store: OrderStore = info.context["order_store"]
    return await order_store.get_job(request.delivery_uuid)


async def get_handling_robot_by_request(request: Request, info: strawberry.types.Info) -> Robot | None:
    """Resolve handling Robot from Request."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_robot(request.handling_robot_name)

# Field resolvers for Job type (called from types.py)

async def get_request_by_job(job: Job, info: strawberry.types.Info) -> Request | None:
    """Resolve Request from Job."""
    if job.request_uuid is None:
        return None
    order_store: OrderStore = info.context["order_store"]
    return await order_store.get_request(job.request_uuid)


async def get_handling_robot_by_job(job: Job, info: strawberry.types.Info) -> Robot:
    """Resolve handling Robot from Job."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_robot(job.handling_robot_name)


# Field resolvers for Robot type (called from types.py)
async def get_robot_cells_by_robot(robot: Robot, info: strawberry.types.Info) -> list[RobotCell]:
    """Resolve robot cells from Robot."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_robot_cells(robot.name)

async def get_current_job_by_robot(robot: Robot, info: strawberry.types.Info) -> Job | None:
    """Resolve current Job from Robot."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_current_job(robot.name)

async def get_job_queue_by_robot(robot: Robot, info: strawberry.types.Info) -> list[Job]:
    """Resolve job queue from Robot."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_job_queue(robot.name)


# Field resolvers for RobotCell type (called from types.py)
async def get_holding_by_robot_cell(robot_cell: RobotCell, info: strawberry.types.Info) -> Job | None:
    """Resolve holding Request from RobotCell."""
    if robot_cell.holding_uuid is None:
        return None
    order_store: OrderStore = info.context["order_store"]
    return await order_store.get_job(robot_cell.holding_uuid)
