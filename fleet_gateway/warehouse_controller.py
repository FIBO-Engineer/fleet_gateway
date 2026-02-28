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
        RequestIDInput,
        RequestAliasInput,
        JobOrderInput,
        RequestOrderInput,
        AssignmentInput,
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

    # def get_node(self, node_specifier: int | str) -> Node:
    #     return self.route_oracle.get_node(node_specifier)

    # def get_nodes(self, node_specifiers: list[int] | list[str]) -> list[Node]:
    #     return self.route_oracle.get_nodes(node_specifiers)

    # def get_pd_nodes(self, node_specifiers: tuple[int, int] | tuple[str, str]) -> tuple[Node, Node]:
    #     nodes = self.route_oracle.get_nodes(list(node_specifiers))
    #     return (nodes[0], nodes[1])

    async def accept_job_order(self, job_order: JobOrderInput) -> JobOrderResult:
        from fleet_gateway.api.types import Job, JobOrderResult
        target_node = self.route_oracle.get_node(job_order.target_node_alias or job_order.target_node_id)

        if self.fleet_handler.get_robot(job_order.robot_name) is None:
            raise RuntimeError(f"Robot {job_order.robot_name} not found")
        
        if job_order.operation == JobOperation.TRAVEL and target_node.node_type != NodeType.WAYPOINT:
            raise RuntimeError(f"TRAVEL operation rejected: node {target_node.id}/{target_node.alias} is {target_node.node_type} not WAYPOINT")

        # Try to insert data in order_store
        job = Job(uuid=uuid4(), status=OrderStatus.QUEUING, operation=job_order.operation,
                  target_node=target_node, request_uuid=None, handling_robot_name=job_order.robot_name)
        if not await self.order_store.set_job(job):
            return JobOrderResult(success=False, message="Unable to set job in order_store", job=None)

        # Just put into the queue
        self.fleet_handler.assign_job(job_order.robot_name, job)
        return JobOrderResult(success=True, message="Successfully save job into order_store and robot", job=job)
    

    async def create_request_jobs(self, pd_nodes: tuple[Node, Node], robot_name: str) -> tuple[Request, Job, Job]:
        request_uuid: UUID = uuid4()
        pickup_job = Job(uuid=uuid4(), status=OrderStatus.QUEUING, operation=JobOperation.PICKUP,
                         target_node=pd_nodes[0], request_uuid=request_uuid, handling_robot_name=robot_name)
        if not await self.order_store.set_job(pickup_job):
            raise RuntimeError("Unable to store pickup job")

        delivery_job = Job(uuid=uuid4(), status=OrderStatus.QUEUING, operation=JobOperation.DELIVERY,
                           target_node=pd_nodes[1], request_uuid=request_uuid, handling_robot_name=robot_name)
        if not await self.order_store.set_job(delivery_job):
            raise RuntimeError("Unable to store delivery job")

        request = Request(uuid=request_uuid, pickup_uuid=pickup_job.uuid,
                          delivery_uuid=delivery_job.uuid, handling_robot_name=robot_name)
        if not await self.order_store.set_request(request):
            raise RuntimeError("Unable to store request")
        
        return request, pickup_job, delivery_job

    async def accept_request_order(self, request_order: RequestOrderInput) -> RequestOrderResult:
        from fleet_gateway.api.types import RequestOrderResult

        if request_order.request_id is None and request_order.request_alias is None:
            return RequestOrderResult(success=False, message="Either request_id or request_alias must be provided", request=None)

        node_specifiers: list[int] | list[str]
        if request_order.request_id is not None:
            node_specifiers = [request_order.request_id.pickup_node_id, request_order.request_id.delivery_node_id]
        else:
            node_specifiers = [request_order.request_alias.pickup_node_alias, request_order.request_alias.delivery_node_alias]

        pd_nodes: tuple[Node, Node] = tuple(self.route_oracle.get_nodes(node_specifiers))
        request, pickup_job, delivery_job = await self.create_request_jobs(pd_nodes, request_order.robot_name)
        
        self.fleet_handler.assign_job(request_order.robot_name, pickup_job)
        self.fleet_handler.assign_job(request_order.robot_name, delivery_job)
        return RequestOrderResult(success=True, message="Successfully saved request into order_store and robot queue", request=request)

    def create_node_to_robot_dict(self, assignments: list[AssignmentInput]) -> dict[int, str] | dict[str, str]:
        node_to_robot: dict[int, str] | dict[str, str] = {}
        for assignment in assignments:
            if self.fleet_handler.get_robot(assignment.robot_name) is None:
                raise RuntimeError(f"Robot '{assignment.robot_name}' not found in fleet")
            if assignment.route_node_ids is None and assignment.route_node_aliases is None:
                raise RuntimeError(f"Assignment for '{assignment.robot_name}' must provide route_node_ids or route_node_aliases")
            if assignment.route_node_ids is not None and assignment.route_node_aliases is not None:
                raise RuntimeError(f"Assignment for '{assignment.robot_name}' must provide route_node_ids or route_node_aliases, not both")
            
            route_node : list[int] | list[str] = []
            route_node = assignment.route_node_ids or assignment.route_node_aliases

            for node in route_node:
                node_to_robot[node] = assignment.robot_name

        return node_to_robot

    def create_robot_to_node_incides(self, assignments: list[AssignmentInput]) -> dict[str, dict[int, int]] | dict[str, dict[str, int]]:
        robot_to_node_incides: dict[str, dict[int, int]] | dict[str, dict[str, int]] = {}
        for assignment in assignments:
            node_to_idx: dict[int, int] | dict[str, int] = {}
            for idx, node in enumerate(assignment.route_node_ids or assignment.route_node_aliases):
                node_to_idx[node] = idx
            robot_to_node_incides[assignment.robot_name] = node_to_idx
        return robot_to_node_incides

    async def accept_warehouse_order(self, warehouse_order: WarehouseOrderInput) -> WarehouseOrderResult:
        from fleet_gateway.api.types import WarehouseOrderResult

        if warehouse_order.request_ids is None and warehouse_order.request_aliases is None:
            return WarehouseOrderResult(success=False, message="Either request_ids or request_aliases must be provided", requests=[])
        if warehouse_order.request_ids is not None and warehouse_order.request_aliases is not None:
            return WarehouseOrderResult(success=False, message="Provide either request_ids or request_aliases, not both", requests=[])

        use_ids = warehouse_order.request_ids is not None
        node_to_robot : dict[int, str] | dict[str, str] = self.create_node_to_robot_dict(warehouse_order.assignments)
        robot_to_node_indices: dict[str, dict[int, int]] | dict[str, dict[str, int]] = self.create_robot_to_node_incides(warehouse_order.assignments)
        robot_job_route: dict[str, list[Job]] = { asm.robot_name: [None] * len(asm.route_node_ids or asm.route_node_aliases) for asm in warehouse_order.assignments }

        requests: list[Request] = []

        for r in warehouse_order.request_ids or warehouse_order.request_aliases:
            pickup: int | str = r.pickup_node_id if use_ids else r.pickup_node_alias
            delivery: int | str = r.delivery_node_id if use_ids else r.delivery_node_alias
            nodes: tuple[Node, Node] = tuple(self.route_oracle.get_nodes([pickup, delivery]))
            
            if node_to_robot[pickup] != node_to_robot[delivery]:
                return WarehouseOrderResult(success=False, message="Pickup and delivery locations mismatched", requests=[])
            
            robot_name = node_to_robot[pickup]

            request, pickup_job, delivery_job = await self.create_request_jobs(nodes, node_to_robot[pickup])
            
            robot_job_route[robot_name][robot_to_node_indices[robot_name][pickup]] = pickup_job
            robot_job_route[robot_name][robot_to_node_indices[robot_name][delivery]] = delivery_job            
            requests.append(request)

        for robot, job_route in robot_job_route.items():
            for job in job_route:
                self.fleet_handler.assign_job(robot, job)

        return WarehouseOrderResult(success=True, message=f"Successfully created {len(requests)} request(s)", requests=requests)

    async def cancel_job_order(self, uuid: UUID) -> Job | None:
        job = await self.order_store.get_job(uuid)
        if job is None:
            return None
        if job.status in (OrderStatus.COMPLETED, OrderStatus.CANCELED, OrderStatus.FAILED):
            return job
        self.fleet_handler.remove_queued_job(job.handling_robot_name, uuid)
        job.status = OrderStatus.CANCELED
        await self.order_store.set_job(job)
        return job

    async def cancel_job_orders(self, uuids: list[UUID]) -> list[Job]:
        results = [await self.cancel_job_order(uuid) for uuid in uuids]
        return [job for job in results if job is not None]

    async def cancel_request_order(self, uuid: UUID) -> Request | None:
        request = await self.order_store.get_request(uuid)
        if request is None:
            return None
        await self.cancel_job_order(request.pickup_uuid)
        await self.cancel_job_order(request.delivery_uuid)
        return request

    async def cancel_request_orders(self, uuids: list[UUID]) -> list[Request]:
        results = [await self.cancel_request_order(uuid) for uuid in uuids]
        return [r for r in results if r is not None]
