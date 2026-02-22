"""
Combined GraphQL schema for Fleet Gateway.

This module combines all GraphQL components (queries, mutations, subscriptions)
into a single Strawberry schema for use with FastAPI.
"""
from __future__ import annotations
import strawberry
from uuid import UUID

from fleet_gateway.api.types import Robot, Job, Request, JobOrderInput, JobOrderResult, RequestOrderInput, RequestOrderResult, WarehouseOrderInput, WarehouseOrderResult, RobotCellInput
from fleet_gateway.warehouse_controller import WarehouseController
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
    """All mutations go to warehouse_controller, these job and request will be queued"""
    # Three level of interfaces
    @strawberry.mutation
    async def send_job_order(self, info: strawberry.types.Info, job_order: JobOrderInput) -> JobOrderResult:
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.accept_job_order(job_order)

    @strawberry.mutation
    async def send_request_order(self, info: strawberry.types.Info, request_order: RequestOrderInput) -> RequestOrderResult:
        """Submit a single warehouse request with robot assignment."""
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.accept_request_order(request_order)

    @strawberry.mutation
    async def send_warehouse_order(self, info: strawberry.types.Info, warehouse_order: WarehouseOrderInput) -> WarehouseOrderResult:
        """Submit multiple warehouse requests and robot assignments."""
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.accept_warehouse_order(warehouse_order)

    # @strawberry.mutation
    # async def activate(self, info: strawberry.types.Info, robot_name: str, enable: bool) -> Robot:
    #     """Enable or disable a robot to take commands from queue."""
    #     warehouse_controller: WarehouseController = info.context["warehouse_controller"]
    #     return await warehouse_controller.activate(robot_name, enable)

    @strawberry.mutation
    async def cancel_job(self, info: strawberry.types.Info, uuid: UUID) -> Job | None:
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.cancel_job_order(uuid)
    
    @strawberry.mutation
    async def cancel_jobs(self, info: strawberry.types.Info, uuids: list[UUID]) -> list[Job]:
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.cancel_job_orders(uuids)
    
    @strawberry.mutation
    async def cancel_request(self, info: strawberry.types.Info, uuid: UUID) -> Request | None:
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.cancel_request_order(uuid)

    @strawberry.mutation
    async def cancel_requests(self, info: strawberry.types.Info, uuids: list[UUID]) -> list[Request]:
        warehouse_controller: WarehouseController = info.context["warehouse_controller"]
        return await warehouse_controller.cancel_request_orders(uuids)
    
    @strawberry.mutation
    async def free_robot_cell(self, info: strawberry.types.Info, robot_cell: RobotCellInput) -> Request | None:
        fleet_handler: FleetHandler = info.context["fleet_handler"]
        return await fleet_handler.free_cell(robot_cell)

# Create the combined GraphQL schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
)
