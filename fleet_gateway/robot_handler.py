from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import TYPE_CHECKING

import redis.asyncio as redis
from roslibpy import ActionClient, Goal, Ros, Message, Topic

from fleet_gateway.enums import WarehouseOperation, RobotStatus
from fleet_gateway.models import RobotState

if TYPE_CHECKING:
    from fleet_gateway.fleet_orchestrator import FleetOrchestrator


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
        self.current_goal: Goal | None = None
        self.orchestrator: FleetOrchestrator | None = None  # Set by FleetOrchestrator after initialization

        # Robot state (all operational state in one place)
        self.state = RobotState(
            name=name,
            robot_cell_heights=cell_heights
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

    def find_free_cell(self, shelf_height: float, occupied_cells: list[bool]) -> int:
        """Find best free cell matching shelf height."""
        free_indices = (i for i, occupied in enumerate(occupied_cells) if not occupied)
        try:
            return min(free_indices, key=lambda i: abs(self.state.robot_cell_heights[i] - shelf_height))
        except ValueError:
            return -1  # No free cell

    async def send_job(self, job: dict) -> bool:
        """Send job to robot via ROS action."""
        if self.state.current_job is not None:
            raise RuntimeError("Current job in progress, cannot send new job")

        # Accept both int and enum for operation
        operation = job['operation']
        if isinstance(operation, WarehouseOperation):
            operation_value = operation.value
        else:
            operation_value = operation

        nodes = job['nodes']

        # Get target_cell from job (provided by FleetOrchestrator)
        target_cell: int = job.get('target_cell', -1)

        # Convert nodes to ROS message format
        ros_nodes = [
            {
                'id': node['id'],
                'alias': node.get('alias', ''),
                'x': node['x'],
                'y': node['y'],
                'height': node.get('height', 0.0),
                'node_type': node['node_type']
            }
            for node in nodes
        ]

        goal_msg = Message({
            'nodes': ros_nodes,
            'operation': operation_value,
            'robot_cell': target_cell
        })

        # Create goal
        goal = Goal(self.warehouse_cmd_action_client, goal_msg)
        self.current_goal = goal
        self.state.current_job = job

        # Set robot status to BUSY
        self.state.robot_status = RobotStatus.BUSY
        await self._persist_to_redis()

        # Send goal with callbacks
        def on_result(result):
            asyncio.create_task(self._on_job_result(result, operation_value, target_cell))

        def on_feedback(feedback):
            asyncio.create_task(self._on_job_feedback(feedback))

        def on_error(error):
            asyncio.create_task(self._on_job_error(error))

        goal.send(on_result=on_result, on_feedback=on_feedback, on_error=on_error)
        return True

    async def _on_job_result(self, result, operation: int, target_cell: int):
        """Handle job completion result"""
        print(f"[{self.state.name}] Job completed with result: {result}")

        # Extract job_uuid from completed job
        job_uuid = self.state.current_job.get('job_uuid', 'unknown') if self.state.current_job else 'unknown'

        # Clear current job
        self.state.current_job = None
        self.current_goal = None

        # Set robot status to IDLE
        self.state.robot_status = RobotStatus.IDLE

        # Persist to Redis and publish update
        await self._persist_to_redis()
        await self._publish_update()

        # Notify orchestrator to handle next job (if orchestrator is set)
        if self.orchestrator:
            await self.orchestrator.on_robot_job_completed(
                self.state.name,
                job_uuid,
                operation,
                target_cell
            )

    async def _on_job_feedback(self, feedback):
        """Handle job feedback"""
        print(f"[{self.state.name}] Feedback: last_seen_id={feedback.get('last_seen_id')}, moving={feedback.get('moving_component')}")

        # Update last seen node
        if 'last_seen_id' in feedback:
            self.state.mobile_base_status.last_seen.id = feedback['last_seen_id']
            await self._persist_to_redis()

    async def _on_job_error(self, error):
        """Handle job error"""
        print(f"[{self.state.name}] Error: {error}")
        self.state.current_job = None
        self.current_goal = None
        self.state.robot_status = RobotStatus.ERROR
        await self._persist_to_redis()
        await self._publish_update()

    async def cancel_current_job(self) -> None:
        """Cancel the currently executing job"""
        if self.current_goal is not None:
            self.current_goal.cancel()
            self.state.current_job = None
            self.current_goal = None
            self.state.robot_status = RobotStatus.IDLE
            await self._persist_to_redis()
            await self._publish_update()
        else:
            raise RuntimeError("No job to cancel")

    async def set_inactive(self) -> None:
        """Manually set robot to INACTIVE status (user disabled)"""
        if self.current_goal is not None:
            await self.cancel_current_job()
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
        """Save robot state to Redis"""
        # Convert entire state to dict for Redis
        state_dict = asdict(self.state)

        # Convert enum to value for Redis storage
        state_dict['robot_status'] = str(self.state.robot_status.value)

        robot_data = {
            'name': state_dict['name'],
            'robot_cell_heights': json.dumps(state_dict['robot_cell_heights']),
            'robot_status': state_dict['robot_status'],
            'mobile_base_status': json.dumps(state_dict['mobile_base_status']),
            'piggyback_state': json.dumps(state_dict['piggyback_state']),
            'current_job': json.dumps(state_dict['current_job']) if state_dict['current_job'] else '',
            'jobs': json.dumps(state_dict['jobs'])
        }

        await self.redis_client.hset(f"robot:{self.state.name}", mapping=robot_data)

    async def _publish_update(self):
        """Publish update to trigger subscriptions"""
        await self.redis_client.publish(f"robot:{self.state.name}:update", "updated")

    async def initialize_in_redis(self):
        """Initialize robot state in Redis"""
        await self._persist_to_redis()
