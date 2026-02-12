"""
Fleet Orchestrator - Central coordinator for robot fleet management.

This class acts as a facade between the API layer and robot handlers,
providing a clean interface for fleet-level operations and encapsulating
robot handler internals.
"""

import json
import redis.asyncio as redis
from uuid import uuid4

from fleet_gateway.robot_handler import RobotHandler
from fleet_gateway.models import RobotState, Job, Node
from fleet_gateway.enums import RobotStatus, WarehouseOperation, RequestStatus, NodeType


class FleetOrchestrator:
    """Central coordinator for robot fleet management and job dispatching."""

    def __init__(self, robot_handlers: list[RobotHandler], redis_client: redis.Redis):
        """Initialize fleet orchestrator with robot handlers and Redis client."""
        self.robots: dict[str, RobotHandler] = {
            handler.state.name: handler for handler in robot_handlers
        }
        self.redis = redis_client

        # Set orchestrator reference on each robot handler
        for handler in robot_handlers:
            handler.orchestrator = self

    # === Robot Access ===

    def get_robot(self, robot_name: str) -> RobotHandler | None:
        """Get robot handler by name."""
        return self.robots.get(robot_name)

    def get_all_robot_names(self) -> list[str]:
        """Get all robot names in the fleet."""
        return list(self.robots.keys())

    def get_available_robots(self) -> list[str]:
        """Get robots available for work (IDLE, no current job)."""
        return [
            name for name, handler in self.robots.items()
            if handler.state.robot_status == RobotStatus.IDLE
            and handler.state.current_job is None
        ]

    def get_robot_state(self, robot_name: str) -> RobotState | None:
        """Get robot state by name."""
        handler = self.get_robot(robot_name)
        return handler.state if handler else None

    # === Job Management ===

    async def assign_job(
        self,
        robot_name: str,
        job: Job,
        request_uuid: str | None = None # None for TRAVEL task
    ) -> bool:
        """
        Assign job to robot (queues if busy, allocates cells).

        Args:
            robot_name: Target robot name
            job: Job object with uuid, operation, nodes, target_cell
            request_uuid: Optional warehouse request UUID for tracking

        Returns:
            True if job was assigned/queued successfully
        """
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        # Compute target_cell based on operation
        target_cell = -1
        if job.operation == WarehouseOperation.PICKUP:
            # Find free cell for pickup
            shelf_height = job.nodes[-1].height if job.nodes[-1].height is not None else 0.0
            target_cell = handler.find_free_cell(shelf_height)
            if target_cell == -1:
                raise RuntimeError(f"No free cell available for pickup on robot '{robot_name}'")
        elif job.operation == WarehouseOperation.DELIVERY:
            # Find cell holding this request
            if not request_uuid:
                raise RuntimeError("request_uuid is required for DELIVERY operation")
            target_cell = handler.find_cell_with_request(request_uuid)
            if target_cell == -1:
                raise RuntimeError(f"Request {request_uuid} not found in any cell of robot '{robot_name}'")

        # Create final job with computed target_cell and request_uuid
        job_with_cell = Job(
            uuid=job.uuid,
            operation=job.operation,
            nodes=job.nodes,
            target_cell=target_cell,
            request_uuid=request_uuid
        )

        # Persist job to Redis
        await self._persist_job(job_with_cell)

        # If robot is idle, send job immediately
        if handler.state.current_job is None:
            await handler.send_job(job_with_cell)
        else:
            # Robot is busy, queue the job (store UUID only)
            handler.state.jobs.append(job_with_cell.uuid)

        return True

    async def cancel_job(self, robot_name: str) -> bool:
        """Cancel currently executing job."""
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        await handler.cancel_current_job()
        return True

    async def clear_job_queue(self, robot_name: str) -> int:
        """Clear all queued jobs and return count."""
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        count = len(handler.state.jobs)
        handler.state.jobs.clear()
        return count

    # === Robot Control ===

    async def set_robot_enabled(self, robot_name: str, enabled: bool) -> bool:
        """Enable or disable robot (disable cancels current job)."""
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        if enabled:
            await handler.set_active()
        else:
            await handler.set_inactive()
        return True

    # === Fleet Status ===

    def get_fleet_status(self) -> dict[str, dict]:
        """Get status of all robots in the fleet."""
        return {
            name: {
                'status': handler.state.robot_status.name,
                'has_current_job': handler.state.current_job is not None,
                'queued_jobs': len(handler.state.jobs),
                'position': {
                    'x': handler.state.mobile_base_status.x,
                    'y': handler.state.mobile_base_status.y,
                    'a': handler.state.mobile_base_status.a,
                }
            }
            for name, handler in self.robots.items()
        }

    def get_busy_robots(self) -> list[str]:
        """Get robots currently executing jobs."""
        return [
            name for name, handler in self.robots.items()
            if handler.state.robot_status == RobotStatus.BUSY
        ]

    def get_idle_robots(self) -> list[str]:
        """Get idle robots."""
        return [
            name for name, handler in self.robots.items()
            if handler.state.robot_status == RobotStatus.IDLE
        ]

    # === Job Queue Management ===

    async def on_robot_job_completed(self, robot_name: str, job_uuid: str, operation: int, target_cell: int) -> None:
        """Handle job completion: update cells, process next queued job."""
        handler = self.get_robot(robot_name)
        if not handler:
            return

        # Fetch completed job to get request_uuid
        completed_job = await self._fetch_job(job_uuid)
        request_uuid = completed_job.request_uuid if completed_job else None

        # Update cell holdings based on operation
        from fleet_gateway.enums import WarehouseOperation
        if operation == WarehouseOperation.PICKUP.value and target_cell >= 0:
            handler.allocate_cell(target_cell, request_uuid)
        elif operation == WarehouseOperation.DELIVERY.value and target_cell >= 0:
            handler.release_cell(target_cell)

        # Process next queued job if available
        if handler.state.jobs:
            next_job_uuid = handler.state.jobs.pop(0)
            # Fetch full job from Redis
            next_job = await self._fetch_job(next_job_uuid)
            if next_job:
                # request_uuid is already in the job
                await self.assign_job(robot_name, next_job, next_job.request_uuid)
        # Future enhancement: Could rebalance fleet here
        # await self._rebalance_fleet()

    # === Advanced Operations ===

    def find_optimal_robot(self, target_position: tuple[float, float]) -> str | None:
        """Find closest available robot to target position."""
        available = self.get_available_robots()
        if not available:
            return None

        target_x, target_y = target_position

        # Find closest available robot
        def distance(robot_name: str) -> float:
            handler = self.robots[robot_name]
            robot_x = handler.state.mobile_base_status.x
            robot_y = handler.state.mobile_base_status.y
            return ((robot_x - target_x) ** 2 + (robot_y - target_y) ** 2) ** 0.5

        return min(available, key=distance)

    # === Request Management ===

    async def submit_requests_and_assignments(
        self,
        requests: list,
        assignments: list,
        graph_oracle,
        graph_id: int
    ) -> list[str]:
        """Submit warehouse requests and robot assignments with path planning."""
        created_request_uuids = []

        # Create requests in Redis
        request_map = {}
        for req_input in requests:
            request_uuid = str(uuid4())
            created_request_uuids.append(request_uuid)
            request_map[req_input.pickup_id] = request_uuid

            pickup_job_uuid = str(uuid4())
            delivery_job_uuid = str(uuid4())

            pickup_job_data = {
                'uuid': pickup_job_uuid,
                'operation': WarehouseOperation.PICKUP.value,
                'nodes': [],
                'target_cell': -1
            }
            delivery_job_data = {
                'uuid': delivery_job_uuid,
                'operation': WarehouseOperation.DELIVERY.value,
                'nodes': [],
                'target_cell': -1
            }
            request_data = {
                'uuid': request_uuid,
                'pickup': json.dumps(pickup_job_data),
                'delivery': json.dumps(delivery_job_data),
                'handler': '',
                'request_status': str(RequestStatus.IN_PROGRESS.value)
            }
            await self.redis.hset(f"request:{request_uuid}", mapping=request_data)
            await self.redis.publish(f"request:{request_uuid}:update", "updated")

        # Process assignments
        for assignment in assignments:
            robot_name = assignment.robot
            target_node_ids = assignment.jobs

            if self.get_robot(robot_name) is None:
                raise ValueError(f"Robot '{robot_name}' not found")

            current_node_id = await self._get_robot_current_node(robot_name)
            if current_node_id is None:
                raise RuntimeError(f"Robot '{robot_name}' position not found")

            for target_node_id in target_node_ids:
                operation = WarehouseOperation.TRAVEL.value
                request_uuid = None

                # Check if pickup
                if target_node_id in request_map:
                    operation = WarehouseOperation.PICKUP.value
                    request_uuid = request_map[target_node_id]
                    await self.redis.hset(f"request:{request_uuid}", 'handler', robot_name)
                    await self.redis.publish(f"request:{request_uuid}:update", "updated")
                # Check if delivery
                else:
                    for req_input in requests:
                        if req_input.delivery_id == target_node_id:
                            operation = WarehouseOperation.DELIVERY.value
                            request_uuid = request_map.get(req_input.pickup_id)
                            break

                # Query graph oracle for path
                path_node_ids = graph_oracle.getShortestPathById(graph_id, current_node_id, target_node_id)
                path_nodes = graph_oracle.getNodesByIds(graph_id, path_node_ids)

                # Convert to Node objects
                job_nodes = [
                    Node(
                        id=node.id,
                        alias=node.alias if node.alias else None,
                        x=node.x,
                        y=node.y,
                        height=node.height if node.height else None,
                        node_type=NodeType(node.node_type.value if hasattr(node.node_type, 'value') else node.node_type)
                    )
                    for node in path_nodes
                ]

                # Create Job object
                job = Job(
                    uuid=str(uuid4()),
                    operation=WarehouseOperation(operation),
                    nodes=job_nodes,
                    target_cell=-1  # Will be computed in assign_job
                )
                await self.assign_job(robot_name, job, request_uuid)
                current_node_id = target_node_id

        return created_request_uuids

    async def _get_robot_current_node(self, robot_name: str) -> int | None:
        """Get robot's current node ID from Redis."""
        robot_data = await self.redis.hgetall(f"robot:{robot_name}")
        if not robot_data or 'mobile_base_status' not in robot_data:
            return None
        try:
            mobile_base_status = json.loads(robot_data['mobile_base_status'])
            return mobile_base_status['last_seen']['id']
        except (KeyError, ValueError, json.JSONDecodeError):
            return None

    async def _persist_job(self, job: Job) -> None:
        """Persist job to Redis at job:{uuid}."""
        from fleet_gateway.models import job_to_dict
        job_data = job_to_dict(job)
        await self.redis.hset(f"job:{job.uuid}", mapping=job_data)

    async def _fetch_job(self, job_uuid: str) -> Job | None:
        """Fetch job from Redis by UUID."""
        from fleet_gateway.models import dict_to_job
        job_data = await self.redis.hgetall(f"job:{job_uuid}")
        if not job_data:
            return None
        # Convert bytes to strings if needed
        job_dict = {k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in job_data.items()}
        # Parse nodes JSON string
        import json
        job_dict['nodes'] = json.loads(job_dict['nodes'])
        return dict_to_job(job_dict)
