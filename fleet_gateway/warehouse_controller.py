from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
import asyncio

from fleet_gateway.enums import JobOperation, NodeType, OrderStatus

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

from loguru import logger


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
                    logger.info("Updated job {} status to {} in order_store", job.uuid, job.status)
                else:
                    logger.error("Unable to update job {} in order_store", job.uuid)

        self._updater_task = asyncio.create_task(handle_job_updater(self.job_updater))

    def validate_job(self, robot_name: str, operation: JobOperation | None = None,
                     target_node_id: int | None = None, target_node_alias: str | None = None) -> Node | None:
        # Resolve node by id or alias
        if target_node_id is not None:
            target_node = self.route_oracle.get_node_by_id(target_node_id)
        elif target_node_alias is not None:
            target_node = self.route_oracle.get_node_by_alias(target_node_alias)
        else:
            return None

        if target_node is None:
            return None

        # Check if robot exists
        if self.fleet_handler.get_robot(robot_name) is None:
            return None

        # TRAVEL operation must target a waypoint
        if operation == JobOperation.TRAVEL and target_node.node_type != NodeType.WAYPOINT:
            logger.warning("TRAVEL operation rejected: node {} is {} not WAYPOINT",
                           target_node_id or target_node_alias, target_node.node_type)
            return None

        return target_node

    async def accept_job_order(self, job_order: JobOrderInput) -> JobOrderResult:
        from fleet_gateway.api.types import Job, JobOrderResult
        if job_order.target_node_id is None and job_order.target_node_alias is None:
            return JobOrderResult(success=False, message="Either target_node_id or target_node_alias must be provided", job=None)

        if (target_node := self.validate_job(job_order.robot_name, job_order.operation,
                                             job_order.target_node_id, job_order.target_node_alias)) is None:
            return JobOrderResult(success=False, message=f"Unable to validate robot {job_order.robot_name} or node {job_order.target_node_id or job_order.target_node_alias}", job=None)

        # Try to insert data in order_store
        job = Job(uuid=uuid4(), status=OrderStatus.QUEUING, operation=job_order.operation,
                  target_node=target_node, request_uuid=None, handling_robot_name=job_order.robot_name)
        if not await self.order_store.set_job(job):
            return JobOrderResult(success=False, message="Unable to set job in order_store", job=None)

        # Just put into the queue
        self.fleet_handler.assign_job(job_order.robot_name, job)
        return JobOrderResult(success=True, message="Successfully save job into order_store and robot", job=job)

    async def accept_request_order(self, request_order: RequestOrderInput) -> RequestOrderResult:
        from fleet_gateway.api.types import Job, Request, RequestOrderResult
        # This appends request and delivery job queue to the specified robot
        pd_nodes: list[Node] = []
        for target_node_id in [request_order.request.pickup_node_id, request_order.request.delivery_node_id]:
            if (target_node := self.validate_job(request_order.robot_name, target_node_id)) is None:
                return RequestOrderResult(success=False, message=f"Unable to validate robot {request_order.robot_name} or node {target_node_id}", request=None)
            else:
                pd_nodes.append(target_node)

        request_uuid : UUID = uuid4()
        pickup_job = Job(uuid=uuid4(), status=OrderStatus.QUEUING, operation=JobOperation.PICKUP,
                         target_node=pd_nodes[0], request_uuid=request_uuid, handling_robot_name=request_order.robot_name)
        if not await self.order_store.set_job(pickup_job):
            return RequestOrderResult(success=False, message=f"Unable to store pickup job", request=None)

        delivery_job = Job(uuid=uuid4(), status=OrderStatus.QUEUING, operation=JobOperation.DELIVERY,
                           target_node=pd_nodes[1], request_uuid=request_uuid, handling_robot_name=request_order.robot_name)
        if not await self.order_store.set_job(delivery_job):
            return RequestOrderResult(success=False, message=f"Unable to store delivery job", request=None)

        request = Request(uuid=request_uuid, pickup_uuid=pickup_job.uuid,
                          delivery_uuid=delivery_job.uuid, handling_robot_name=request_order.robot_name)
        if not await self.order_store.set_request(request):
            return RequestOrderResult(success=False, message=f"Unable to store request job", request=None)

        # In robot layer, they don't care about request
        self.fleet_handler.assign_job(request_order.robot_name, pickup_job)
        self.fleet_handler.assign_job(request_order.robot_name, delivery_job)

        return RequestOrderResult(success=True, message=f"Successfully save request into order_store and queue in robot", request=request)

    async def accept_warehouse_order(self, warehouse_order: WarehouseOrderInput) -> WarehouseOrderResult:
        from fleet_gateway.api.types import WarehouseOrderResult
        return WarehouseOrderResult(success=False, message="Not implemented", requests=[])

    async def cancel_job_order(self, uuid: UUID) -> Job | None:
        return None

    async def cancel_job_orders(self, uuids: list[UUID]) -> list[Job]:
        return []

    async def cancel_request_order(self, uuid: UUID) -> Request | None:
        return None

    async def cancel_request_orders(self, uuids: list[UUID]) -> list[Request]:
        return []
