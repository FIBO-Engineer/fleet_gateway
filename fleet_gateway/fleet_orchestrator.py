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
from fleet_gateway.job_handler import JobHandler
from fleet_gateway.api.types import Job, Node, Robot
from fleet_gateway.enums import RobotStatus, WarehouseOperation, RequestStatus, NodeType


class FleetOrchestrator:
    """Central coordinator for robot fleet management and job dispatching."""

    def __init__(self, robot_handlers: list[RobotHandler], redis_client: redis.Redis):
        """Initialize fleet orchestrator with robot handlers and Redis client."""
        self.robots: dict[str, RobotHandler] = {
            robot.state.name: robot for robot in robot_handlers
        }
        self.redis = redis_client
        self.job_handler = JobHandler(redis_client)

        # Set orchestrator reference on each robot handler
        for robot in robot_handlers:
            robot.orchestrator = self

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
            name for name, robot in self.robots.items()
            if robot.state.robot_status == RobotStatus.IDLE
            and robot.state.current_job is None
        ]

    def get_robot_state(self, robot_name: str) -> Robot | None:
        """Get robot state by name."""
        robot = self.get_robot(robot_name)
        return robot.state if robot else None

    # === Job Management ===

    async def assign_job(self, robot: RobotHandler, job: Job) -> bool:
        """Assign job to robot (queues if busy, allocates cells)."""
        # Create final job with computed target_cell
        job_with_cell = Job(
            uuid=job.uuid,
            operation=job.operation,
            nodes=job.nodes,
            target_cell=robot.find_target_cell(job),
            request_uuid=job.request_uuid
        )

        # Persist job to Redis
        await self.job_handler.upsert_job(job_with_cell)

        # If robot is idle, send job immediately
        if robot.state.current_job is None and robot.state.robot_status == RobotStatus.IDLE:
            await robot.send_job(job_with_cell)
        else:
            # Robot is busy, queue the job (store full Job object)
            robot.state.jobs.append(job_with_cell)

        return True

    async def cancel_job(self, robot: RobotHandler) -> str: # UUID of canceled job
        """Cancel currently executing job (will become a dangling job)"""
        return await robot.cancel_current_job()

    async def clear_job_queue(self, robot: RobotHandler) -> int:
        """Clear all queued jobs and return count"""
        return await robot.clear_job_queue()

    # === Robot Control ===
    async def set_robot_enabled(self, robot: RobotHandler, enabled: bool) -> bool:
        """Enable or disable robot (disable cancels current job)"""
        if enabled:
            await robot.set_active()
        else:
            await robot.set_inactive()
        return True

    # === Job Queue Management ===

    async def on_robot_job_completed(self, robot: RobotHandler) -> None:
        """Handle job completion: update cells, process next queued job."""
        # Process next queued job if available
        if robot.state.jobs:
            next_job = robot.state.jobs.pop(0)
            await self.assign_job(robot, next_job)

    # === Request Management ===

    async def submit_requests_and_assignments(
        self, 
        requests: list,
        assignments: list,
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

    # === Fleet Status ===

    # def get_fleet_status(self) -> dict[str, dict]:
    #     """Get status of all robots in the fleet."""
    #     return {
    #         name: {
    #             'status': robot.state.robot_status.name,
    #             'has_current_job': robot.state.current_job is not None,
    #             'queued_jobs': len(robot.state.jobs),
    #             'position': {
    #                 'x': robot.state.mobile_base_status.x,
    #                 'y': robot.state.mobile_base_status.y,
    #                 'a': robot.state.mobile_base_status.a,
    #             }
    #         }
    #         for name, robot in self.robots.items()
    #     }

    # def get_busy_robots(self) -> list[str]:
    #     """Get robots currently executing jobs."""
    #     return [
    #         name for name, robot in self.robots.items()
    #         if robot.state.robot_status == RobotStatus.BUSY
    #     ]

    # def get_idle_robots(self) -> list[str]:
    #     """Get idle robots."""
    #     return [
    #         name for name, robot in self.robots.items()
    #         if robot.state.robot_status == RobotStatus.IDLE
    #     ]

    # === Advanced Operations ===

    # def find_optimal_robot(self, target_position: tuple[float, float]) -> str | None:
    #     """Find closest available robot to target position."""
    #     available = self.get_available_robots()
    #     if not available:
    #         return None

    #     target_x, target_y = target_position

    #     # Find closest available robot
    #     def distance(robot_name: str) -> float:
    #         robot = self.robots[robot_name]
    #         robot_x = robot.state.mobile_base_status.x
    #         robot_y = robot.state.mobile_base_status.y
    #         return ((robot_x - target_x) ** 2 + (robot_y - target_y) ** 2) ** 0.5

    #     return min(available, key=distance)
