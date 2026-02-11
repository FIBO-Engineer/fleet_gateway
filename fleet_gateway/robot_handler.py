import asyncio
import json
from typing import Optional
from uuid import UUID

import redis.asyncio as redis
from roslibpy import ActionClient, Goal, GoalStatus, Ros, Message, Topic

from fleet_gateway.enums import WarehouseOperation, RobotStatus


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

        self.name: str = name
        self.cell_heights: list[float] = cell_heights
        self.redis_client: redis.Redis = redis_client

        # State tracking
        self.holding_request_uuids: list[Optional[str]] = [None for _ in range(len(cell_heights))]
        self.current_job: Optional[dict] = None
        self.job_queue: list[dict] = []
        self.current_goal: Optional[Goal] = None

        # Robot state
        self.robot_status: int = RobotStatus.OFFLINE.value
        self.mobile_base_state: dict = {
            'last_seen': {'id': 0, 'x': 0.0, 'y': 0.0, 'height': 0.0, 'node_type': 0},
            'x': 0.0,
            'y': 0.0,
            'a': 0.0
        }
        self.piggyback_state: dict = {
            'axis_0': 0.0,
            'axis_1': 0.0,
            'axis_2': 0.0,
            'gripper': False
        }

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
            self.mobile_base_state['x'] = pose['position']['x']
            self.mobile_base_state['y'] = pose['position']['y']
            # Extract yaw from quaternion
            z = pose['orientation']['z']
            w = pose['orientation']['w']
            self.mobile_base_state['a'] = 2.0 * (w * z)  # Simplified yaw extraction

            # Persist to Redis asynchronously
            asyncio.create_task(self._persist_to_redis())

    def _on_piggyback_update(self, message):
        """Callback for piggyback state updates"""
        if 'position' in message and len(message['position']) >= 3:
            self.piggyback_state['axis_0'] = message['position'][0]
            self.piggyback_state['axis_1'] = message['position'][1]
            self.piggyback_state['axis_2'] = message['position'][2]

            # Persist to Redis asynchronously
            asyncio.create_task(self._persist_to_redis())

    def find_free_cell(self, shelf_height: float) -> int:
        """Find the best free cell for a given shelf height"""
        free_indices = (i for i, uuid in enumerate(self.holding_request_uuids) if uuid is None)
        try:
            return min(free_indices, key=lambda i: abs(self.cell_heights[i] - shelf_height))
        except ValueError:
            return -1  # No free cell

    def find_storing_cell(self, request_uuid: str) -> int:
        """Find the cell storing a specific request by UUID"""
        for i, uuid in enumerate(self.holding_request_uuids):
            if uuid == request_uuid:
                return i
        return -1

    async def send_job(self, job: dict, request_uuid: Optional[str] = None) -> bool:
        """
        Send a job to the robot via ROS action.

        Args:
            job: Job dictionary with 'operation' (int or WarehouseOperation) and 'nodes' fields
            request_uuid: UUID of the request this job belongs to (required for PICKUP/DELIVERY)

        Returns:
            True if job was sent successfully, False otherwise
        """
        if self.current_job is not None:
            raise RuntimeError("Current job in progress, cannot send new job")

        # Accept both int and enum for operation
        operation = job['operation']
        if isinstance(operation, WarehouseOperation):
            operation_value = operation.value
        else:
            operation_value = operation

        nodes = job['nodes']

        # Determine target cell based on operation
        target_cell: int = -1
        if operation_value == WarehouseOperation.PICKUP.value:
            target_cell = self.find_free_cell(nodes[-1].get('height', 0.0))
            if target_cell == -1:
                raise RuntimeError("No free cell available for pickup")
        elif operation_value == WarehouseOperation.DELIVERY.value:
            if not request_uuid:
                raise RuntimeError("request_uuid is required for DELIVERY operation")
            target_cell = self.find_storing_cell(request_uuid)
            if target_cell == -1:
                raise RuntimeError(f"Request {request_uuid} not found in any cell")

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
        self.current_job = job

        # Set robot status to BUSY
        self.robot_status = RobotStatus.BUSY.value
        await self._persist_to_redis()

        # Send goal with callbacks
        def on_result(result):
            asyncio.create_task(self._on_job_result(result, operation, target_cell, request_uuid))

        def on_feedback(feedback):
            asyncio.create_task(self._on_job_feedback(feedback))

        def on_error(error):
            asyncio.create_task(self._on_job_error(error))

        goal.send(on_result=on_result, on_feedback=on_feedback, on_error=on_error)
        return True

    async def _on_job_result(self, result, operation: int, target_cell: int, request_uuid: Optional[str]):
        """Handle job completion result"""
        print(f"[{self.name}] Job completed with result: {result}")

        # Update holdings based on operation
        if operation == WarehouseOperation.PICKUP.value and target_cell >= 0:
            self.holding_request_uuids[target_cell] = request_uuid
        elif operation == WarehouseOperation.DELIVERY.value and target_cell >= 0:
            self.holding_request_uuids[target_cell] = None

        # Clear current job
        self.current_job = None
        self.current_goal = None

        # Set robot status to IDLE
        self.robot_status = RobotStatus.IDLE.value

        # Persist to Redis and publish update
        await self._persist_to_redis()
        await self._publish_update()

        # Process next job in queue if available
        if self.job_queue:
            next_job = self.job_queue.pop(0)
            # Extract request_uuid if it was stored in the job
            next_request_uuid = next_job.pop('request_uuid', None)
            await self.send_job(next_job, next_request_uuid)

    async def _on_job_feedback(self, feedback):
        """Handle job feedback"""
        print(f"[{self.name}] Feedback: last_seen_id={feedback.get('last_seen_id')}, moving={feedback.get('moving_component')}")

        # Update last seen node
        if 'last_seen_id' in feedback:
            self.mobile_base_state['last_seen']['id'] = feedback['last_seen_id']
            await self._persist_to_redis()

    async def _on_job_error(self, error):
        """Handle job error"""
        print(f"[{self.name}] Error: {error}")
        self.current_job = None
        self.current_goal = None
        self.robot_status = RobotStatus.ERROR.value
        await self._persist_to_redis()
        await self._publish_update()

    async def cancel_current_job(self) -> None:
        """Cancel the currently executing job"""
        if self.current_goal is not None:
            self.current_goal.cancel()
            self.current_job = None
            self.current_goal = None
            self.robot_status = RobotStatus.IDLE.value
            await self._persist_to_redis()
            await self._publish_update()
        else:
            raise RuntimeError("No job to cancel")

    async def set_inactive(self) -> None:
        """Manually set robot to INACTIVE status (user disabled)"""
        if self.current_goal is not None:
            await self.cancel_current_job()
        self.robot_status = RobotStatus.INACTIVE.value
        await self._persist_to_redis()
        await self._publish_update()

    async def set_active(self) -> None:
        """Re-enable robot from INACTIVE or ERROR status"""
        if self.robot_status in (RobotStatus.INACTIVE.value, RobotStatus.ERROR.value):
            self.robot_status = RobotStatus.IDLE.value
            await self._persist_to_redis()
            await self._publish_update()

    async def _persist_to_redis(self):
        """Save robot state to Redis"""
        robot_data = {
            'name': self.name,
            'robot_cell_heights': json.dumps(self.cell_heights),
            'robot_status': str(self.robot_status),
            'mobile_base_status': json.dumps(self.mobile_base_state),
            'piggyback_state': json.dumps(self.piggyback_state),
            'current_job': json.dumps(self.current_job) if self.current_job else '',
            'jobs': json.dumps(self.job_queue)
        }

        await self.redis_client.hset(f"robot:{self.name}", mapping=robot_data)

    async def _publish_update(self):
        """Publish update to trigger subscriptions"""
        await self.redis_client.publish(f"robot:{self.name}:update", "updated")

    async def initialize_in_redis(self):
        """Initialize robot state in Redis"""
        await self._persist_to_redis()
