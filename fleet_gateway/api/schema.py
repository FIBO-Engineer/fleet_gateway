"""
Combined GraphQL schema for Fleet Gateway.

This module combines all GraphQL components (queries, mutations, subscriptions)
into a single Strawberry schema for use with FastAPI.
"""

import strawberry
from uuid import UUID

from fleet_gateway.api.types import Robot, Request, Job, RequestInput, AssignmentInput, OrderResult
from fleet_gateway.fleet_handler import FleetHandler
from fleet_gateway.order_store import OrderStore

@strawberry.type
class Query:

    @strawberry.field
    async def robot(self, info: strawberry.types.Info, name: str) -> Robot | None:
        """Get a specific robot by name."""
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        return await fleet_handler.get_robot(name)

    @strawberry.field
    async def robots(self, info: strawberry.types.Info) -> list[Robot]:
        """Get all robots in the fleet."""
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        return await fleet_handler.get_robots()

    @strawberry.field
    async def request(self, info: strawberry.types.Info, uuid: UUID) -> Request | None:
        """Get a specific request by UUID."""
        order_store: OrderStore = info.context["order_store"]
        return await order_store.get_request(uuid)

    @strawberry.field
    async def requests(self, info: strawberry.types.Info) -> list[Request]:
        """Get all warehouse requests."""
        order_store: OrderStore = info.context["order_store"]
        return await order_store.get_requests()
    
    @strawberry.field
    async def job(self, info: strawberry.types.Info, uuid: UUID) -> Job | None:
        """Get a specific job by UUID."""
        order_store: OrderStore = info.context["order_store"]
        return await order_store.get_job(uuid)

    @strawberry.field
    async def jobs(self, info: strawberry.types.Info) -> list[Job]:
        """Get all warehouse jobs."""
        order_store: OrderStore = info.context["order_store"]
        return await order_store.get_jobs()

@strawberry.type
class Mutation:
    """All mutations go to warehouse_controller"""

    @strawberry.mutation
    async def send_robot_order(self, info: strawberry.types.Info, request: RequestInput, robot_name: str) -> OrderResult:
        """Submit a single warehouse request with robot assignment."""
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.send_robot_order()

    @strawberry.mutation
    async def send_fleet_order(self, info: strawberry.types.Info, requests: list[RequestInput], assignments: list[AssignmentInput]) -> OrderResult:
        """Submit multiple warehouse requests and robot assignments."""
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.send_fleet_order()

    @strawberry.mutation
    async def activate(self, info: strawberry.types.Info, robot_name: str, enable: bool) -> Robot:
        """Enable or disable a robot to take commands from queue."""
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.activate(robot_name, enable)

    @strawberry.mutation
    async def cancel_request(self, info: strawberry.types.Info, request_uuid: UUID) -> UUID:
        """Cancel a warehouse request."""
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        raise await warehouse_controller.cancel(request_uuid)
    

# Create the combined GraphQL schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
)
