"""
GraphQL resolvers for Fleet Gateway.

Contains both query/mutation resolvers (called from schema.py)
and field resolvers (called from types.py).
"""

import strawberry
from uuid import UUID
# from typing import TYPE_CHECKING

# if TYPE_CHECKING:
from fleet_gateway.api.types import Job, Robot, Request, OrderResult, RequestInput, AssignmentInput
from fleet_gateway.fleet_handler import FleetHandler
from fleet_gateway.order_store import OrderStore


# Query resolvers (called from schema.py)

def get_robots(info: strawberry.types.Info) -> list[Robot]:
    """Get all robots in the fleet."""
    fleet_handler = info.context["fleet_handler"]
    raise NotImplementedError()


def get_requests(info: strawberry.types.Info) -> list[Request]:
    """Get all warehouse requests."""
    order_store = info.context["order_store"]
    raise NotImplementedError()


def get_robot_by_name(info: strawberry.types.Info, name: str) -> Robot | None:
    """Get a specific robot by name."""
    fleet_handler = info.context["fleet_handler"]
    raise NotImplementedError()


def get_request_by_uuid(info: strawberry.types.Info, uuid: UUID) -> Request | None:
    """Get a specific request by UUID."""
    order_store = info.context["order_store"]
    raise NotImplementedError()


# Mutation resolvers (called from schema.py)

def send_robot_order(info: strawberry.types.Info, request: RequestInput, robot_name: str) -> OrderResult:
    """Submit a single warehouse request with robot assignment."""
    warehouse_controller = info.context["warehouse_controller"]
    raise NotImplementedError()


def send_fleet_order(info: strawberry.types.Info, requests: list[RequestInput], assignments: list[AssignmentInput]) -> OrderResult:
    """Submit multiple warehouse requests and robot assignments."""
    warehouse_controller = info.context["warehouse_controller"]
    raise NotImplementedError()


def activate_robot(info: strawberry.types.Info, robot_name: str, enable: bool) -> Robot:
    """Enable or disable a robot to take commands from queue."""
    warehouse_controller = info.context["warehouse_controller"]
    raise NotImplementedError()


def cancel_request(info: strawberry.types.Info, request_uuid: UUID) -> UUID:
    """Cancel a warehouse request."""
    warehouse_controller = info.context["warehouse_controller"]
    raise NotImplementedError()


# Field resolvers for Job type (called from types.py)

async def get_request_by_job(root: Job, info: strawberry.types.Info) -> Request | None:
    """Resolve Request from Job."""
    return None


# Field resolvers for Robot type (called from types.py)

async def get_holdings_by_robot(root: Robot, info: strawberry.types.Info) -> list[Request | None]:
    """Resolve holdings (Request objects per cell) from Robot."""
    return []


async def get_current_job_by_robot(root: Robot, info: strawberry.types.Info) -> Job | None:
    """Resolve current Job from Robot."""
    return None


async def get_job_queue_by_robot(root: Robot, info: strawberry.types.Info) -> list[Job]:
    """Resolve job queue from Robot."""
    return []


# Field resolvers for Request type (called from types.py)

async def get_pickup_job_by_request(root: Request, info: strawberry.types.Info) -> Job:
    """Resolve pickup Job from Request."""
    raise NotImplementedError()


async def get_delievery_job_by_request(root: Request, info: strawberry.types.Info) -> Job:
    """Resolve delivery Job from Request."""
    raise NotImplementedError()


async def get_handling_robot_by_request(root: Request, info: strawberry.types.Info) -> Robot | None:
    """Resolve handling Robot from Request."""
    return None


# Field resolvers for OrderResult type (called from types.py)
async def get_new_requests(root: OrderResult, info: strawberry.types.Info) -> list[Request]:
    """Resolve newly created Requests from OrderResult."""
    return []
