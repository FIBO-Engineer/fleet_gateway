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
from fleet_gateway.robot_cell_manager import RobotCellManager
from fleet_gateway.models import RobotState
from fleet_gateway.enums import RobotStatus, WarehouseOperation, RequestStatus


class FleetOrchestrator:
    """Central coordinator for robot fleet management and job dispatching."""

    def __init__(self, robot_handlers: list[RobotHandler], redis_client: redis.Redis):
        """Initialize fleet orchestrator with robot handlers and Redis client."""
        self.robots: dict[str, RobotHandler] = {
            handler.state.name: handler for handler in robot_handlers
        }
        self.redis = redis_client

        # Cell allocation manager
        self.cell_manager = RobotCellManager(robot_handlers)

        # Track job_uuid to request_uuid mapping
        self.job_to_request_map: dict[str, str | None] = {}

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
        job: dict,
        request_uuid: str | None = None
    ) -> bool:
        """Assign job to robot (queues if busy, generates job_uuid, allocates cells)."""
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        # Prepare job with metadata
        job_prepared = job.copy()

        # Generate unique job UUID for tracking
        job_uuid = str(uuid4())
        job_prepared['job_uuid'] = job_uuid

        # Track job_uuid -> request_uuid mapping (not passed to handler)
        if request_uuid:
            self.job_to_request_map[job_uuid] = request_uuid

        # Compute target_cell based on operation
        operation = job['operation']
        from fleet_gateway.enums import WarehouseOperation
        if isinstance(operation, WarehouseOperation):
            operation_value = operation.value
        else:
            operation_value = operation

        target_cell = -1
        if operation_value == WarehouseOperation.PICKUP.value:
            # Find free cell for pickup
            shelf_height = job['nodes'][-1].get('height', 0.0)
            target_cell = self.cell_manager.find_free_cell(robot_name, shelf_height)
            if target_cell == -1:
                raise RuntimeError(f"No free cell available for pickup on robot '{robot_name}'")
        elif operation_value == WarehouseOperation.DELIVERY.value:
            # Find cell holding this request
            if not request_uuid:
                raise RuntimeError("request_uuid is required for DELIVERY operation")
            target_cell = self.cell_manager.find_cell_with_request(robot_name, request_uuid)
            if target_cell == -1:
                raise RuntimeError(f"Request {request_uuid} not found in any cell of robot '{robot_name}'")

        # Add target_cell to job
        job_prepared['target_cell'] = target_cell

        # If robot is idle, send job immediately
        if handler.state.current_job is None:
            await handler.send_job(job_prepared)
        else:
            # Robot is busy, queue the job
            handler.state.jobs.append(job_prepared)

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

    async def set_robot_inactive(self, robot_name: str) -> bool:
        """Set robot to INACTIVE status and cancel current job."""
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        await handler.set_inactive()
        return True

    async def set_robot_active(self, robot_name: str) -> bool:
        """Re-enable robot from INACTIVE or ERROR status."""
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        await handler.set_active()
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

        # Lookup request_uuid from job mapping
        request_uuid = self.job_to_request_map.pop(job_uuid, None)

        # Update cell holdings based on operation
        from fleet_gateway.enums import WarehouseOperation
        if operation == WarehouseOperation.PICKUP.value and target_cell >= 0:
            self.cell_manager.allocate_cell(robot_name, target_cell, request_uuid)
        elif operation == WarehouseOperation.DELIVERY.value and target_cell >= 0:
            self.cell_manager.release_cell(robot_name, target_cell)

        # Process next queued job if available
        if handler.state.jobs:
            next_job = handler.state.jobs.pop(0)
            # Extract request_uuid from next_job if it was queued with one
            request_uuid_for_next = next_job.get('request_uuid')
            # Remove request_uuid from job before passing to assign_job
            next_job_clean = {k: v for k, v in next_job.items() if k != 'request_uuid'}
            await self.assign_job(robot_name, next_job_clean, request_uuid_for_next)
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

            pickup_job_data = {
                'operation': WarehouseOperation.PICKUP.value,
                'nodes': []
            }
            delivery_job_data = {
                'operation': WarehouseOperation.DELIVERY.value,
                'nodes': []
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

                # Convert to job format
                job_nodes = [
                    {
                        'id': node.id,
                        'alias': node.alias if node.alias else '',
                        'x': node.x,
                        'y': node.y,
                        'height': node.height if node.height else 0.0,
                        'node_type': node.node_type.value if hasattr(node.node_type, 'value') else node.node_type
                    }
                    for node in path_nodes
                ]

                job = {'operation': operation, 'nodes': job_nodes}
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
