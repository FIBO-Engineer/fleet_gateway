from uuid import UUID, uuid4
from fleet_gateway.api.types import (
    Job,
    Request,
    JobOrderInput,
    RequestOrderInput,
    WarehouseOrderInput,
    JobOrderResult,
    RequestOrderResult,
    WarehouseOrderResult,
)

from fleet_gateway.fleet_handler import FleetHandler
from fleet_gateway.order_store import OrderStore
from fleet_gateway.route_oracle import RouteOracle

class WarehouseController():
    def __init__(self, fleet_handler: FleetHandler, order_store: OrderStore, route_oracle: RouteOracle):
        self.fleet_handler = fleet_handler
        self.order_store = order_store
        self.route_oracle = route_oracle

    async def accept_job_order(self, job_order: JobOrderInput) -> JobOrderResult:
        target_node = self.route_oracle.getNodeById(job_order.target_node_id)
        job = Job(uuid4(), job_order.operation, target_node, None, job_order.robot_name)
        if await self.order_store.set_job(job):
            # Pass job to robot
            self.fleet_handler.
        else:
            return JobOrderResult(False, "Unable to set job in order store", None)
        raise NotImplementedError

    async def accept_request_order(self, request_order: RequestOrderInput) -> RequestOrderResult:
        raise NotImplementedError

    async def accept_warehouse_order(self, warehouse_order: WarehouseOrderInput) -> WarehouseOrderResult:
        raise NotImplementedError

    async def reject_job_order(self, uuid: UUID) -> Job | None:
        raise NotImplementedError

    async def reject_job_orders(self, uuids: list[UUID]) -> list[Job]:
        raise NotImplementedError

    async def reject_request_order(self, uuid: UUID) -> Request | None:
        raise NotImplementedError

    async def reject_request_orders(self, uuids: list[UUID]) -> list[Request]:
        raise NotImplementedError
