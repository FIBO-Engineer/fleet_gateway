"""
Fleet Orchestrator - Central coordinator for robot fleet management.

This class acts as a facade between the API layer and robot handlers,
providing a clean interface for fleet-level operations and encapsulating
robot handler internals.
"""

import redis.asyncio as redis
from uuid import uuid4, UUID

from fleet_gateway.robot_handler import RobotHandler
from fleet_gateway.graph_oracle import GraphOracle
from fleet_gateway.job_store import JobStore
from fleet_gateway.request_store import RequestStore
from fleet_gateway.api.types import Job, Robot, Request, RequestInput, AssignmentInput
from fleet_gateway.enums import RobotStatus, WarehouseOperation, RequestStatus


class FleetOrchestrator:
    """Central coordinator for robot fleet management and job dispatching."""

    def __init__(self, robot_handlers: list[RobotHandler], redis_client: redis.Redis, graph_oracle: GraphOracle):
        """Initialize fleet orchestrator with robot handlers and Redis client."""
        self.robots: dict[str, RobotHandler] = {
            robot.state.name: robot for robot in robot_handlers
        }
        self.redis = redis_client
        self.requests = RequestStore(redis_client)
        self.jobs = JobStore(redis_client)
        self.graph_oracle = graph_oracle

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
        await self.jobs.upsert_job(job_with_cell)

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
        request_inputs: list[RequestInput],
        assignments: list[AssignmentInput],
    ) -> list[UUID]:
        """Submit warehouse requests and robot assignments with path planning."""

        requests: list[Request] = []

        for req in request_inputs:
            for robot_name, route_node_ids in assignments:
                if req.pickup_id in route_node_ids and req.delivery_id in route_node_ids:
                    # Late routing for inactive scenario
                    request_uuid = uuid4()
                    pickup_job = Job(uuid4(), WarehouseOperation.PICKUP, self.graph_oracle.getNodesByIds(req.pickup_id), -1, request_uuid)
                    delivery_job = Job(uuid4(), WarehouseOperation.DELIVERY, self.graph_oracle.getNodesByIds(req.pickup_id), -1, request_uuid)
                    requests.append(Request(request_uuid, pickup_job, delivery_job, self.get_robot(robot_name), RequestStatus.IN_PROGRESS))

        uuids = await self.requests.upsert_all(requests, self.jobs)
        return uuids

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
