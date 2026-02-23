from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
import asyncio

from fleet_gateway.enums import JobOperation, OrderStatus

if TYPE_CHECKING:
    from fleet_gateway.api.types import (
        Node,
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
    def __init__(self, job_updater: asyncio.Queue, fleet_handler: FleetHandler, order_store: OrderStore, route_oracle: RouteOracle):
        self.job_updater = job_updater
        self.fleet_handler = fleet_handler
        self.order_store = order_store
        self.route_oracle = route_oracle

        # Function to handle in redis
        async def handle_job_updater(queue: asyncio.Queue):
            while True:
                job = await queue.get()
                if await self.order_store.set_job(job):
                    print("Updated job status in order store")
                else:
                    print("Unable to update job in order store")

        asyncio.create_task(handle_job_updater(self.job_updater))

    def validate_job(self, robot_name: str, target_node_id: int) -> Node | None:
        # Check if node exists
        target_node = self.route_oracle.getNodeById(target_node_id)
        if target_node is None:
            return None #JobOrderResult(False, f"Unable to find target node id: {target_node_id}", None)
        
        # Check if robot exists
        if self.fleet_handler.get_robot(robot_name) is None:
            return None #JobOrderResult(False, f"Unable to find robot name: {robot_name}", None)
        
        return target_node

    async def accept_job_order(self, job_order: JobOrderInput) -> JobOrderResult:
        from fleet_gateway.api.types import Job, JobOrderResult
        if (target_node := self.validate_job(job_order.robot_name, job_order.target_node_id)) is None:
            return JobOrderResult(False, f"Unable to validate robot {job_order.robot_name} or node {job_order.target_node_id}", None)

        # Try to insert data in order_store
        job = Job(uuid4(), OrderStatus.QUEUING, job_order.operation, target_node, None, job_order.robot_name)
        if not await self.order_store.set_job(job):
            return JobOrderResult(False, "Unable to set job in order store", None)

        # Just put into the queue
        self.fleet_handler.assign_job(job_order.robot_name, job)
        return JobOrderResult(True, "Successfully save job into order store and robot", job)
            
    async def accept_request_order(self, request_order: RequestOrderInput) -> RequestOrderResult:
        from fleet_gateway.api.types import Job, Request, RequestOrderResult
        # This appends request and delivery job queue to the specified robot
        pd_nodes: list[Node] = []
        for target_node_id in [request_order.request.pickup_node_id, request_order.request.delivery_node_id]:
            if (target_node := self.validate_job(request_order.robot_name, target_node_id)) is None:
                return RequestOrderResult(False, f"Unable to validate robot {request_order.robot_name} or node {target_node_id}", None)
            else:
                pd_nodes.append(target_node)

        request_uuid : UUID = uuid4()
        pickup_job = Job(uuid4(), OrderStatus.QUEUING, JobOperation.PICKUP, pd_nodes[0], request_uuid, request_order.robot_name)
        if not await self.order_store.set_job(pickup_job):
            return RequestOrderResult(False, f"Unable to store pickup job", None)

        delivery_job = Job(uuid4(), OrderStatus.QUEUING, JobOperation.DELIVERY, pd_nodes[1], request_uuid, request_order.robot_name)
        if not await self.order_store.set_job(delivery_job):
            return RequestOrderResult(False, f"Unable to store delivery job", None)
        
        request = Request(request_uuid, pickup_job.uuid, delivery_job.uuid, request_order.robot_name)
        if not await self.order_store.set_request(request):
            return RequestOrderResult(False, f"Unable to store request job", None)
        
        # In robot layer, they don't care about request
        self.fleet_handler.assign_job(request_order.robot_name, pickup_job)
        self.fleet_handler.assign_job(request_order.robot_name, delivery_job)

        return RequestOrderResult(True, f"Successfully save request into order store and queue in robot", request)

    async def accept_warehouse_order(self, warehouse_order: WarehouseOrderInput) -> WarehouseOrderResult:
        raise NotImplementedError

    async def cancel_job_order(self, uuid: UUID) -> Job | None:
        raise NotImplementedError

    async def cancel_job_orders(self, uuids: list[UUID]) -> list[Job]:
        raise NotImplementedError

    async def cancel_request_order(self, uuid: UUID) -> Request | None:
        raise NotImplementedError

    async def cancel_request_orders(self, uuids: list[UUID]) -> list[Request]:
        raise NotImplementedError
