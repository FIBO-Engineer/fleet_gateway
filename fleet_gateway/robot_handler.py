from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import redis.asyncio as redis
from roslibpy import ActionClient, Goal, Ros, Message, Topic

from fleet_gateway.enums import RobotStatus, NodeType
from fleet_gateway.api.types import Job, Node, MobileBaseState, PiggybackState, Robot

if TYPE_CHECKING:
    from fleet_gateway.fleet_orchestrator import FleetOrchestrator

logger = logging.getLogger(__name__)


class RobotHandler(Ros):
    """
    Robot handler that communicates with a robot via ROS WarehouseCommand action
    and maintains state in Redis.
    """

    def __init__(
        self,
        name: str,
        host_ip: str,
        port: int,
        cell_heights: list[float],
        redis_client: redis.Redis
    ) -> None:
        super().__init__(host=host_ip, port=port)
        self.run(1.0)

        # Infrastructure (RobotHandler-specific)
        self.redis_client: redis.Redis = redis_client
        self.ros_action_goal: Goal | None = None
        self.orchestrator: FleetOrchestrator | None = None  # Set by FleetOrchestrator after initialization

        # Robot state (all operational state in one place)
        self.state = Robot(
            name=name,
            robot_cell_heights=cell_heights,
            robot_status=RobotStatus.OFFLINE,
            mobile_base_status=MobileBaseState(
                last_seen=Node(id=0, alias=None, x=0.0, y=0.0, height=0.0, node_type=NodeType.WAYPOINT),
                x=0.0,
                y=0.0,
                a=0.0
            ),
            piggyback_state=PiggybackState(
                axis_0=0.0,
                axis_1=0.0,
                axis_2=0.0,
                gripper=False
            ),
            cell_holdings=[None] * len(cell_heights),
            holdings=[],
            current_job=None,
            jobs=[]
        )

        # Set up the action client
        self.warehouse_cmd_action_client = ActionClient(
            self,
            '/warehouse_command',
            'warehouse_server/WarehouseCommandAction'
        )

        # Subscribe to robot state topics (if available)
        self._setup_state_subscribers()

    def _setup_state_subscribers(self):
        """Set up ROS topic subscribers for robot state"""
        # Subscribe to mobile base state topic
        self.mobile_base_topic = Topic(
            self,
            '/mobile_base/state',
            'geometry_msgs/PoseStamped'
        )
        self.mobile_base_topic.subscribe(self._on_mobile_base_update)

        # Subscribe to piggyback state topic
        self.piggyback_topic = Topic(
            self,
            '/piggyback/state',
            'sensor_msgs/JointState'
        )
        self.piggyback_topic.subscribe(self._on_piggyback_update)

    def _on_mobile_base_update(self, message):
        """Callback for mobile base state updates"""
        if 'pose' in message:
            pose = message['pose']
            self.state.mobile_base_status.x = pose['position']['x']
            self.state.mobile_base_status.y = pose['position']['y']
            # Extract yaw from quaternion
            z = pose['orientation']['z']
            w = pose['orientation']['w']
            self.state.mobile_base_status.a = 2.0 * (w * z)  # Simplified yaw extraction

            # Persist to Redis asynchronously
            asyncio.create_task(self._persist_to_redis())

    def _on_piggyback_update(self, message):
        """Callback for piggyback state updates"""
        if 'position' in message and len(message['position']) >= 3:
            self.state.piggyback_state.axis_0 = message['position'][0]
            self.state.piggyback_state.axis_1 = message['position'][1]
            self.state.piggyback_state.axis_2 = message['position'][2]

            # Persist to Redis asynchronously
            asyncio.create_task(self._persist_to_redis())
    
    # === Location ===
    def get_current_node(self):
        """Get robot's current node ID from Redis."""
        return self.state.mobile_base_status.last_seen

    # === Cell Management ===

    def find_free_cell(self, shelf_height: float) -> int:
        """Find best free cell matching shelf height."""
        free_indices = (i for i, cell in enumerate(self.state.cell_holdings) if cell is None)
        try:
            return min(
                free_indices,
                key=lambda i: abs(self.state.robot_cell_heights[i] - shelf_height)
            )
        except ValueError:
            return -1  # No free cell

    def find_cell_with_request(self, request_uuid: str) -> int:
        """Find cell index holding the given request."""
        try:
            return self.state.cell_holdings.index(request_uuid)
        except ValueError:
            return -1

    def allocate_cell(self, cell_idx: int, request_uuid: str):
        """Allocate a cell for a request."""
        if 0 <= cell_idx < len(self.state.cell_holdings):
            self.state.cell_holdings[cell_idx] = request_uuid

    def release_cell(self, cell_idx: int):
        """Release a cell after delivery."""
        if 0 <= cell_idx < len(self.state.cell_holdings):
            self.state.cell_holdings[cell_idx] = None

    def get_occupied_cells(self) -> list[bool]:
        """Get list of which cells are occupied."""
        return [cell is not None for cell in self.state.cell_holdings]
    

    def find_target_cell(self, job: Job) -> int:
        """Find appropriate target cell for job based on operation type"""
        from fleet_gateway.enums import WarehouseOperation

        match job.operation:
            case WarehouseOperation.PICKUP:
                shelf_height = job.nodes[-1].height if job.nodes[-1].height is not None else 0.0
                target_cell = self.find_free_cell(shelf_height)
                if target_cell == -1:
                    raise RuntimeError(f"No free cell available for pickup on robot '{self.state.name}'")
                return target_cell

            case WarehouseOperation.DELIVERY:
                if not job.request_uuid:
                    raise RuntimeError("request_uuid is required for DELIVERY operation")
                target_cell = self.find_cell_with_request(job.request_uuid)
                if target_cell == -1:
                    raise RuntimeError(f"Request {job.request_uuid} not found in any cell of robot '{self.state.name}'")
                return target_cell

            case _:
                return -1  # TRAVEL jobs don't need a cell

    async def send_job(self, job: Job) -> bool:
        """Send job to robot via ROS action."""
        if self.state.current_job is not None:
            raise RuntimeError("Current job in progress, cannot send new job")

        goal_msg = Message({
            'nodes': [
                        {
                            'id': node.id,
                            'alias': node.alias or '',
                            'x': node.x,
                            'y': node.y,
                            'height': node.height or 0.0,
                            'node_type': node.node_type.value
                        }
                        for node in job.nodes
                    ],
            'operation': job.operation.value,
            'robot_cell': job.target_cell
        })

        # Create goal
        goal = Goal(self.warehouse_cmd_action_client, goal_msg)
        self.ros_action_goal = goal
        self.state.current_job = job  # Store full Job object

        # Set robot status to BUSY
        self.state.robot_status = RobotStatus.BUSY
        await self._persist_to_redis()

        # Send goal with callbacks
        def on_result(result):
            asyncio.create_task(self._on_job_result(result))

        def on_feedback(feedback):
            asyncio.create_task(self._on_job_feedback(feedback))

        def on_error(error):
            asyncio.create_task(self._on_job_error(error))

        goal.send(on_result=on_result, on_feedback=on_feedback, on_error=on_error)
        return True

    async def _on_job_result(self, result):
        """Handle job completion result"""
        logger.info(f"[{self.state.name}] Job {self.state.current_job.uuid} completed with result: {result}")

        # Update cell holdings based on operation
        from fleet_gateway.enums import WarehouseOperation
        if self.state.current_job.target_cell >= 0:
            if self.state.current_job.operation == WarehouseOperation.PICKUP:
                self.allocate_cell(self.state.current_job.target_cell, self.state.current_job.request_uuid)
            elif self.state.current_job.operation == WarehouseOperation.DELIVERY:
                self.release_cell(self.state.current_job.target_cell)

        # Clear current job
        self.state.current_job = None
        self.ros_action_goal = None

        # Set robot status to IDLE
        self.state.robot_status = RobotStatus.IDLE

        # Persist to Redis and publish update
        await self._persist_to_redis()
        await self._publish_update()

        # Notify orchestrator to handle next job (if orchestrator is set)
        if self.orchestrator:
            await self.orchestrator.on_robot_job_completed(self)

    async def _on_job_feedback(self, feedback):
        """Handle job feedback"""
        logger.debug(f"[{self.state.name}] Feedback: last_seen_id={feedback.get('last_seen_id')}, moving={feedback.get('moving_component')}")

        # Update last seen node
        if 'last_seen_id' in feedback:
            self.state.mobile_base_status.last_seen.id = feedback['last_seen_id']
            await self._persist_to_redis()

    async def _on_job_error(self, error):
        """Handle job error"""
        logger.error(f"[{self.state.name}] Job error: {error}")
        self.state.current_job = None
        self.ros_action_goal = None
        self.state.robot_status = RobotStatus.ERROR
        await self._persist_to_redis()
        await self._publish_update()

    async def cancel_current_job(self) -> str:
        """Cancel the currently executing job"""
        if self.ros_action_goal is not None:
            job_id = self.state.current_job.uuid
            self.ros_action_goal.cancel()
            self.state.current_job = None
            self.ros_action_goal = None
            self.state.robot_status = RobotStatus.IDLE
            await self._persist_to_redis()
            await self._publish_update()
            return job_id
        else:
            return -1
    
    async def clear_job_queue(self) -> int:
        """Clear all queued jobs and return count"""
        count = len(self.state.jobs)
        self.state.jobs.clear()
        await self._persist_to_redis()
        await self._publish_update()
        return count

    async def set_inactive(self) -> None:
        """Manually set robot to INACTIVE status (user disabled)"""
        if self.ros_action_goal is not None:
            # await self.cancel_current_job()
            # Won't be inactive if there's job to do
            return
        self.state.robot_status = RobotStatus.INACTIVE
        await self._persist_to_redis()
        await self._publish_update()

    async def set_active(self) -> None:
        """Re-enable robot from INACTIVE or ERROR status"""
        if self.state.robot_status in (RobotStatus.INACTIVE, RobotStatus.ERROR):
            self.state.robot_status = RobotStatus.IDLE
            await self._persist_to_redis()
            await self._publish_update()

    async def _persist_to_redis(self):
        """Save robot state to Redis (jobs stored as UUIDs, full objects kept in memory)"""
        # Convert jobs to UUIDs for Redis (keep full objects in memory)
        current_job_uuid = self.state.current_job.uuid if self.state.current_job else ''
        job_uuids = [job.uuid for job in self.state.jobs]

        # Serialize mobile_base_status
        mobile_base_dict = {
            'last_seen': {
                'id': self.state.mobile_base_status.last_seen.id,
                'alias': self.state.mobile_base_status.last_seen.alias,
                'x': self.state.mobile_base_status.last_seen.x,
                'y': self.state.mobile_base_status.last_seen.y,
                'height': self.state.mobile_base_status.last_seen.height,
                'node_type': self.state.mobile_base_status.last_seen.node_type.value
            },
            'x': self.state.mobile_base_status.x,
            'y': self.state.mobile_base_status.y,
            'a': self.state.mobile_base_status.a
        }

        # Serialize piggyback_state
        piggyback_dict = {
            'axis_0': self.state.piggyback_state.axis_0,
            'axis_1': self.state.piggyback_state.axis_1,
            'axis_2': self.state.piggyback_state.axis_2,
            'gripper': self.state.piggyback_state.gripper
        }

        robot_data = {
            'name': self.state.name,
            'robot_cell_heights': json.dumps(self.state.robot_cell_heights),
            'robot_status': str(self.state.robot_status.value),
            'mobile_base_status': json.dumps(mobile_base_dict),
            'piggyback_state': json.dumps(piggyback_dict),
            'current_job': current_job_uuid,
            'jobs': json.dumps(job_uuids),
            'cell_holdings': json.dumps(self.state.cell_holdings)
        }

        await self.redis_client.hset(f"robot:{self.state.name}", mapping=robot_data)

    async def _publish_update(self):
        """Publish update to trigger subscriptions"""
        await self.redis_client.publish(f"robot:{self.state.name}:update", "updated")

    async def initialize_in_redis(self):
        """Initialize robot state in Redis"""
        await self._persist_to_redis()
