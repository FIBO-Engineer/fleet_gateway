"""
Fleet Orchestrator - Central coordinator for robot fleet management.

This class acts as a facade between the API layer and robot handlers,
providing a clean interface for fleet-level operations and encapsulating
robot handler internals.
"""

import redis.asyncio as redis
from uuid import uuid4

from fleet_gateway.robot_handler import RobotHandler
from fleet_gateway.models import RobotState
from fleet_gateway.enums import RobotStatus


class FleetOrchestrator:
    """
    Manages robot fleet and provides clean API for fleet operations.

    Responsibilities:
    - Robot lifecycle management
    - Job assignment and dispatching
    - Fleet status monitoring
    - Centralized coordination logic
    """

    def __init__(self, robot_handlers: list[RobotHandler], redis_client: redis.Redis):
        """
        Initialize fleet orchestrator.

        Args:
            robot_handlers: List of robot handlers to manage
            redis_client: Redis client for state management
        """
        self.robots: dict[str, RobotHandler] = {
            handler.state.name: handler for handler in robot_handlers
        }
        self.redis = redis_client

        # Track which cell holds which request for each robot
        # robot_name -> list of request_uuids (None if cell is free)
        self.robot_cell_holdings: dict[str, list[str | None]] = {
            handler.state.name: [None] * len(handler.state.robot_cell_heights)
            for handler in robot_handlers
        }

        # Track job_uuid to request_uuid mapping
        self.job_to_request_map: dict[str, str | None] = {}

        # Set orchestrator reference on each robot handler
        for handler in robot_handlers:
            handler.orchestrator = self

    # === Robot Access ===

    def get_robot(self, robot_name: str) -> RobotHandler | None:
        """
        Get robot handler by name.

        Args:
            robot_name: Name of the robot

        Returns:
            RobotHandler if found, None otherwise
        """
        return self.robots.get(robot_name)

    def get_all_robot_names(self) -> list[str]:
        """
        Get names of all robots in the fleet.

        Returns:
            List of robot names
        """
        return list(self.robots.keys())

    def get_available_robots(self) -> list[str]:
        """
        Get list of robots available for work (IDLE status, no current job).

        Returns:
            List of available robot names
        """
        return [
            name for name, handler in self.robots.items()
            if handler.state.robot_status == RobotStatus.IDLE
            and handler.state.current_job is None
        ]

    def get_robot_state(self, robot_name: str) -> RobotState | None:
        """
        Get robot state.

        Args:
            robot_name: Name of the robot

        Returns:
            RobotState if found, None otherwise
        """
        handler = self.get_robot(robot_name)
        return handler.state if handler else None

    # === Job Management ===

    async def assign_job(
        self,
        robot_name: str,
        job: dict,
        request_uuid: str | None = None
    ) -> bool:
        """
        Assign a job to a specific robot.

        Automatically handles queuing if robot is busy.

        Args:
            robot_name: Name of the robot to assign job to
            job: Job dictionary with 'operation' and 'nodes' fields
            request_uuid: Optional UUID of the request this job belongs to

        Returns:
            True if job was assigned/queued successfully

        Raises:
            ValueError: If robot not found
            RuntimeError: If no free cell available or request not found
        """
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
            occupied = [cell is not None for cell in self.robot_cell_holdings[robot_name]]
            shelf_height = job['nodes'][-1].get('height', 0.0)
            target_cell = handler.find_free_cell(shelf_height, occupied)
            if target_cell == -1:
                raise RuntimeError(f"No free cell available for pickup on robot '{robot_name}'")
        elif operation_value == WarehouseOperation.DELIVERY.value:
            # Find cell holding this request
            if not request_uuid:
                raise RuntimeError("request_uuid is required for DELIVERY operation")
            try:
                target_cell = self.robot_cell_holdings[robot_name].index(request_uuid)
            except ValueError:
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
        """
        Cancel the currently executing job for a robot.

        Args:
            robot_name: Name of the robot

        Returns:
            True if job was cancelled

        Raises:
            ValueError: If robot not found
            RuntimeError: If no job to cancel
        """
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        await handler.cancel_current_job()
        return True

    async def clear_job_queue(self, robot_name: str) -> int:
        """
        Clear all queued jobs for a robot.

        Args:
            robot_name: Name of the robot

        Returns:
            Number of jobs cleared

        Raises:
            ValueError: If robot not found
        """
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        count = len(handler.state.jobs)
        handler.state.jobs.clear()
        return count

    # === Robot Control ===

    async def set_robot_inactive(self, robot_name: str) -> bool:
        """
        Set robot to INACTIVE status (user disabled).

        Cancels current job if any.

        Args:
            robot_name: Name of the robot

        Returns:
            True if successful

        Raises:
            ValueError: If robot not found
        """
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        await handler.set_inactive()
        return True

    async def set_robot_active(self, robot_name: str) -> bool:
        """
        Re-enable robot from INACTIVE or ERROR status.

        Args:
            robot_name: Name of the robot

        Returns:
            True if successful

        Raises:
            ValueError: If robot not found
        """
        handler = self.get_robot(robot_name)
        if not handler:
            raise ValueError(f"Robot '{robot_name}' not found")

        await handler.set_active()
        return True

    # === Fleet Status ===

    def get_fleet_status(self) -> dict[str, dict]:
        """
        Get status of all robots in the fleet.

        Returns:
            Dictionary mapping robot names to status info
        """
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
        """
        Get list of robots currently executing jobs.

        Returns:
            List of busy robot names
        """
        return [
            name for name, handler in self.robots.items()
            if handler.state.robot_status == RobotStatus.BUSY
        ]

    def get_idle_robots(self) -> list[str]:
        """
        Get list of idle robots (not busy, not inactive, not errored).

        Returns:
            List of idle robot names
        """
        return [
            name for name, handler in self.robots.items()
            if handler.state.robot_status == RobotStatus.IDLE
        ]

    # === Job Queue Management ===

    async def on_robot_job_completed(self, robot_name: str, job_uuid: str, operation: int, target_cell: int) -> None:
        """
        Called when a robot completes a job.

        Handles cell holdings update and automatic queue processing.

        Args:
            robot_name: Name of the robot that completed the job
            job_uuid: The unique job identifier
            operation: The warehouse operation that was completed
            target_cell: The cell that was used
        """
        handler = self.get_robot(robot_name)
        if not handler:
            return

        # Lookup request_uuid from job mapping
        request_uuid = self.job_to_request_map.pop(job_uuid, None)

        # Update cell holdings based on operation
        from fleet_gateway.enums import WarehouseOperation
        if operation == WarehouseOperation.PICKUP.value and target_cell >= 0:
            self.robot_cell_holdings[robot_name][target_cell] = request_uuid
        elif operation == WarehouseOperation.DELIVERY.value and target_cell >= 0:
            self.robot_cell_holdings[robot_name][target_cell] = None

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
        """
        Find the best robot for a job based on proximity to target.

        Args:
            target_position: (x, y) coordinates of target location

        Returns:
            Name of optimal robot, or None if no available robots
        """
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
