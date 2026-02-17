"""
Fleet Orchestrator - Central coordinator for robot fleet management.

This class acts as a facade between the API layer and robot handlers,
providing a clean interface for fleet-level operations and encapsulating
robot handler internals.
"""

import redis.asyncio as redis
from uuid import uuid4, UUID

from fleet_gateway.robot_connector import RobotConnector
from fleet_gateway.route_oracle import RouteOracle
from fleet_gateway.job_store import JobStore
from fleet_gateway.request_store import RequestStore
from fleet_gateway.api.types import Job, Robot, Request, RequestInput, AssignmentInput
from fleet_gateway.enums import RobotStatus, JobOperation, RequestStatus


class FleetOrchestrator:
    """Central coordinator for robot fleet management and job dispatching."""

    def __init__(self, robot_handlers: list[RobotConnector], redis_client: redis.Redis, graph_oracle: RouteOracle):
        """Initialize fleet orchestrator with robot handlers and Redis client."""
        self.robots: dict[str, RobotConnector] = {
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

    def get_robot(self, robot_name: str) -> RobotConnector | None:
        """Get robot handler by name."""
        return self.robots.get(robot_name)

    def get_all_robot_names(self) -> list[str]:
        """Get all robot names in the fleet."""
        return list(self.robots.keys())

    def get_available_robots(self) -> list[str]:
        """Get robots available for work (IDLE, no current job)."""
        return [
            name for name, robot in self.robots.items()
            if robot.state.status == RobotStatus.IDLE
            and robot.state.current_job is None
        ]

    def get_robot_state(self, robot_name: str) -> Robot | None:
        """Get robot state by name."""
        robot = self.get_robot(robot_name)
        return robot.state if robot else None

    # === Job Management ===

    async def assign_job(self, robot: RobotConnector, job: Job) -> bool:
        """Assign job to robot (queues if busy, allocates cells)."""
        # Create final job with computed target_cell
        job_with_cell = Job(
            uuid=job.uuid,
            operation=job.operation,
            nodes=job.nodes,
            robot_cell=robot.find_target_cell(job),
            request_uuid=job.request_uuid
        )

        # Persist job to Redis
        await self.jobs.upsert_job(job_with_cell)

        # If robot is idle, send job immediately
        if robot.state.current_job is None and robot.state.status == RobotStatus.IDLE:
            await robot.send_job(job_with_cell)
        else:
            # Robot is busy, queue the job (store full Job object)
            robot.state.jobs.append(job_with_cell)

        return True

    async def cancel_job(self, robot: RobotConnector) -> str: # UUID of canceled job
        """Cancel currently executing job (will become a dangling job)"""
        return await robot.cancel_current_job()

    async def clear_job_queue(self, robot: RobotConnector) -> int:
        """Clear all queued jobs and return count"""
        return await robot.clear_job_queue()

    # === Robot Control ===
    async def set_robot_enabled(self, robot: RobotConnector, enabled: bool) -> bool:
        """Enable or disable robot (disable cancels current job)"""
        if enabled:
            await robot.set_active()
        else:
            await robot.set_inactive()
        return True

    # === Job Queue Management ===

    async def on_robot_job_completed(self, robot: RobotConnector) -> None:
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
        """Submit warehouse requests and robot assignments.

        Creates Request and Job objects and persists to Redis.
        Does NOT dispatch jobs - that happens later via assign_job().

        Args:
            request_inputs: List of pickup/delivery pairs (e.g., pickup=7, delivery=10)
            assignments: List of robot routes (e.g., robot="R1", route=[7,8,9,10])

        Returns:
            List of created request UUIDs
        """
        requests: list[Request] = []

        # Build lookup: node_id -> list of assignments containing that node
        node_to_assignments: dict[int, list[tuple[AssignmentInput, int]]] = {}
        for assignment in assignments:
            for idx, node_id in enumerate(assignment.route_node_ids):
                if node_id not in node_to_assignments:
                    node_to_assignments[node_id] = []
                node_to_assignments[node_id].append((assignment, idx))

        # Process each request
        for req in request_inputs:
            # Find assignments containing both pickup and delivery
            pickup_candidates = node_to_assignments.get(req.pickup_id, [])
            delivery_candidates = node_to_assignments.get(req.delivery_id, [])

            # Find assignment that contains both nodes
            matched_assignment = None
            pickup_idx = -1
            delivery_idx = -1

            for p_assignment, p_idx in pickup_candidates:
                for d_assignment, d_idx in delivery_candidates:
                    if p_assignment.robot_name == d_assignment.robot_name:
                        # Same assignment contains both nodes
                        if p_idx < d_idx:  # Pickup comes before delivery
                            matched_assignment = p_assignment
                            pickup_idx = p_idx
                            delivery_idx = d_idx
                            break
                if matched_assignment:
                    break

            # Validation
            if matched_assignment is None:
                raise ValueError(
                    f"No valid assignment found for request: pickup={req.pickup_id}, "
                    f"delivery={req.delivery_id}. Either nodes not in any assignment "
                    f"or delivery comes before pickup."
                )

            # Get robot handler
            robot = self.get_robot(matched_assignment.robot_name)
            if robot is None:
                raise ValueError(f"Robot '{matched_assignment.robot_name}' not found")

            # Fetch node information (just destination nodes, not paths)
            try:
                pickup_nodes = self.graph_oracle.getNodesByIds(None, [req.pickup_id])
                delivery_nodes = self.graph_oracle.getNodesByIds(None, [req.delivery_id])
            except RuntimeError as e:
                raise RuntimeError(f"Failed to fetch nodes from graph: {e}") from e

            if not pickup_nodes or not delivery_nodes:
                raise ValueError(
                    f"Invalid node IDs: pickup={req.pickup_id}, delivery={req.delivery_id}"
                )

            # Create request and jobs
            request_uuid = uuid4()
            pickup_job = Job(
                uuid=str(uuid4()),
                operation=JobOperation.PICKUP,
                nodes=pickup_nodes,  # Just destination node for now
                robot_cell=-1,  # Computed later by assign_job
                request_uuid=str(request_uuid)
            )
            delivery_job = Job(
                uuid=str(uuid4()),
                operation=JobOperation.DELIVERY,
                nodes=delivery_nodes,  # Just destination node for now
                robot_cell=-1,  # Computed later by assign_job
                request_uuid=str(request_uuid)
            )

            request = Request(
                uuid=request_uuid,
                pickup=pickup_job,
                delivery=delivery_job,
                handling_robot=robot.state,  # Robot state object, not RobotHandler
                status=RequestStatus.IN_PROGRESS
            )
            requests.append(request)

        # Persist all requests and jobs to Redis
        uuids = await self.requests.upsert_all(requests, self.jobs)

        # Return UUIDs as UUID objects
        return [UUID(uuid_str) for uuid_str in uuids]

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
