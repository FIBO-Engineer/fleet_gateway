"""
GraphQL field resolvers for Fleet Gateway types.

Contains field resolvers called from types.py to resolve nested GraphQL fields.
"""

import strawberry

from fleet_gateway.api.types import Job, Robot, Request, OrderResult, Node, RobotCell
from order_store import OrderStore, JobStore
from fleet_handler import FleetHandler


# Field resolvers for Request type (called from types.py)

async def get_pickup_job_by_request(root: Request, info: strawberry.types.Info) -> Job:
    """Resolve pickup Job from Request."""
    order_store: OrderStore = info.context["order_store"]
    return order_store.get_pickup_job_by_request(root)


async def get_delievery_job_by_request(root: Request, info: strawberry.types.Info) -> Job:
    """Resolve delivery Job from Request."""
    order_store: OrderStore = info.context["order_store"]
    return order_store.get_delievery_job_by_request(root)


async def get_handling_robot_by_request(root: Request, info: strawberry.types.Info) -> Robot | None:
    """Resolve handling Robot from Request."""
    order_store: OrderStore = info.context["order_store"]
    return order_store.get_handling_robot_by_request(root)


# Field resolvers for Job type (called from types.py)

async def get_target_node_by_job(root: Job, info: strawberry.types.Info) -> Node | None:
    """Resolve target Node from Job."""
    order_store: OrderStore = info.context["order_store"]
    return order_store.get_target_node_by_job(root)


async def get_request_by_job(root: Job, info: strawberry.types.Info) -> Request | None:
    """Resolve Request from Job."""
    order_store: OrderStore = info.context["order_store"]
    return order_store.get_request_by_job(root)


async def get_handling_robot_by_job(root: Job, info: strawberry.types.Info) -> Robot:
    """Resolve handling Robot from Job."""
    order_store: OrderStore = info.context["order_store"]
    return order_store.get_handling_robot_by_job(root)


# Field resolvers for Robot type (called from types.py)
async def get_robot_cells_by_robot(root: Robot, info: strawberry.types.Info) -> list[RobotCell]:
    """Resolve robot cells from Robot."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_robot_cells_by_robot(root)


async def get_current_job_by_robot(root: Robot, info: strawberry.types.Info) -> Job | None:
    """Resolve current Job from Robot."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_current_job_by_robot(root)


async def get_job_queue_by_robot(root: Robot, info: strawberry.types.Info) -> list[Job]:
    """Resolve job queue from Robot."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_job_queue_by_robot(root)


# Field resolvers for RobotCell type (called from types.py)
async def get_robot_by_robot_cell(root: RobotCell, info: strawberry.types.Info) -> Robot:
    """Resolve Robot from RobotCell."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_robot_by_robot_cell(root)


async def get_holding_by_robot_cell(root: RobotCell, info: strawberry.types.Info) -> Request | None:
    """Resolve holding Request from RobotCell."""
    fleet_handler: FleetHandler = info.context["fleet_handler"]
    return fleet_handler.get_holding_by_robot_cell(root)
