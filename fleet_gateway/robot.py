# NOTE: Potential thread-safety risk — shared state (current_job, last_action_status, job_queue)
# is mutated from both the asyncio event loop thread (assign, clear_error) and the roslibpy
# Twisted reactor thread (on_result, on_error callbacks). The put_nowait calls are guarded via
# call_soon_threadsafe, but the other state mutations are not. A full fix requires either
# threading.RLock around all state mutations or restructuring callbacks to dispatch back onto
# the asyncio thread via loop.call_soon_threadsafe before touching shared state.
from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio
import math
from datetime import datetime, timezone, timedelta

from fleet_gateway.route_oracle import RouteOracle
from fleet_gateway.helpers.serializers import node_to_dict

from roslibpy import ActionClient, Goal, GoalStatus, Ros, Topic

from fleet_gateway.enums import OrderStatus, RobotConnectionStatus, RobotActionStatus, JobOperation, RobotCellLevel
from fleet_gateway.models import MobileBaseState, Pose, Tag, PiggybackState, RobotCell

if TYPE_CHECKING:
    from fleet_gateway.api.types import Robot, Job, Node

class RobotConnector(Ros):
    """
    Robot handler that connect to a robot via ROS WarehouseCommand action
    """

    def __init__(self, name: str, host_ip: str, port: int, route_oracle: RouteOracle):
        super().__init__(host=host_ip, port=port)
        self.run(1.0)

        # Robot state (all operational state in one place)
        self.name = name
        self.active_status = True
        self.last_action_status = RobotActionStatus.IDLE
        self.mobile_base_state = MobileBaseState(None, None)
        self.piggyback_state = None

        # Setup the action client
        self.warehouse_cmd_action_client = ActionClient(self, '/warehouse_command', 'warehouse_server/WarehouseCommandAction')
        self.action_future = None
        
        # Setup Mobile Base State Subscribers
        self.odom_topic = Topic(self, '/odom_qr', 'nav_msgs/Odometry')
        self.odom_topic.subscribe(self.odom_qr_callback)
        self.qr_topic = Topic(self, '/qr_id', 'std_msgs/String')
        self.qr_topic.subscribe(self.qr_id_callback)
        
        # Setup Piggyback State Subscribers
        self.piggyback_topic = Topic(self, '/piggyback_state', 'sensor_msgs/JointState')
        self.piggyback_topic.subscribe(self.piggyback_callback)

        # Setup route oracle
        self.route_oracle: RouteOracle = route_oracle

    def odom_qr_callback(self, message):
        """Callback for mobile base state updates"""
        if 'pose' in message:
            position = message['pose']['pose']['position']
            orientation = message['pose']['pose']['orientation']
            a = math.atan2(
                2.0 * (orientation['w'] * orientation['z'] + orientation['x'] * orientation['y']),
                1.0 - 2.0 * (orientation['y'] ** 2 + orientation['z'] ** 2)
            )
            self.mobile_base_state.pose = Pose(datetime.now(timezone(timedelta(hours=7))), position['x'], position['y'], a)

    def qr_id_callback(self, message):
        """"Callback for QR"""
        if 'data' in message:
            self.mobile_base_state.tag = Tag(datetime.now(timezone(timedelta(hours=7))), message['data'])

    def piggyback_callback(self, message):
        """Callback for piggyback state updates"""
        if 'name' in message and 'position' in message:
            try:
                self.piggyback_state = PiggybackState(
                    datetime.now(timezone(timedelta(hours=7))),
                    message["position"][message['name'].index('lift')],
                    message["position"][message['name'].index('turntable')],
                    message["position"][message['name'].index('slide')],
                    message["position"][message['name'].index('hook_left')],
                    message["position"][message['name'].index('hook_right')]
                )
            except (ValueError, IndexError):
                pass

    def send_job(self, job: Job, robot_cell: RobotCellLevel):
        """Send job to robot via ROS action. Use docs/ros_messages/WarehouseCommand.action"""
        """The Job resolve to target node here"""

        if self.mobile_base_state.tag is None:
            raise RuntimeError("Unable to route its location to the destination due to unknown current location")

        # Known current location
        start_node: Node | None = self.route_oracle.getNodeByTagId(tag_id=self.mobile_base_state.tag.qr_id)
        if start_node is None:
            raise RuntimeError("Unable to query start_node")
        
        path_node_ids : list[int] = self.route_oracle.getShortestPathById(start_id=start_node.id, end_id=job.target_node.id)
        if not path_node_ids:
            raise RuntimeError("No path found to target node")
        path_nodes : list[Node] = self.route_oracle.getNodesByIds(node_ids=path_node_ids)
        
        goal = Goal({
            'nodes': [ node_to_dict(node) for node in path_nodes ],
            'operation': job.operation.value,
            'robot_cell': robot_cell.value
        })

        # Send goal with callbacks
        def on_result(result):
            """Handle job completion result"""
            match result["status"]:
                case GoalStatus.SUCCEEDED:
                    self.last_action_status = RobotActionStatus.IDLE
                    self.update_job_status(OrderStatus.COMPLETED)
                case GoalStatus.CANCELED:
                    self.last_action_status = RobotActionStatus.CANCELED
                    self.update_job_status(OrderStatus.CANCELED)
                case GoalStatus.ABORTED:
                    self.last_action_status = RobotActionStatus.ERROR
                    self.update_job_status(OrderStatus.FAILED)
                case _:
                    self.last_action_status = RobotActionStatus.ERROR
                    self.update_job_status(OrderStatus.FAILED)

        def on_feedback(feedback):
            """Handle job feedback"""
            pass

        def on_error(error):
            """Handle job error"""
            print(f"{self.name} error")
            self.last_action_status = RobotActionStatus.ERROR
            self.update_job_status(OrderStatus.FAILED)

        self.last_action_status = RobotActionStatus.OPERATING
        self.update_job_status(OrderStatus.IN_PROGRESS)
        self.warehouse_cmd_action_client.send_goal(goal, on_result, on_feedback, on_error)

    def update_job_status(self, status: OrderStatus):
        pass
    
    def to_robot(self):
        """Convert RobotConnector state to Robot object"""
        from fleet_gateway.api.types import Robot
        return Robot(
            name=self.name,
            connection_status=self.connection_status(),
            last_action_status=self.last_action_status,
            mobile_base_state=self.mobile_base_state,
            piggyback_state=self.piggyback_state
        )
    
    def connection_status(self) -> RobotConnectionStatus:
        return RobotConnectionStatus(self.is_connected)

class RobotHandler(RobotConnector):
    def __init__(self, name: str, host_ip: str, port: int, cell_heights: list[float], job_updater: asyncio.Queue, route_oracle: RouteOracle):
        super().__init__(name, host_ip, port, route_oracle)
        self.cells : list[RobotCell] = [RobotCell(height) for height in cell_heights]
        self.current_job : Job | None = None
        self.current_cell : RobotCellLevel | None = None
        self.job_queue : list[Job] = []
        self.job_updater = job_updater
        self.loop = asyncio.get_running_loop()
    
    def assign(self, job: Job):
        self.job_queue.append(job)
        self.trigger()

    def update_job_status(self, status: OrderStatus):
        if self.current_job is None:
            return
        self.current_job.status = status
        self.loop.call_soon_threadsafe(self.job_updater.put_nowait, self.current_job)
        if status in (OrderStatus.COMPLETED, OrderStatus.CANCELED, OrderStatus.FAILED):
            if status == OrderStatus.COMPLETED and self.current_job.operation == JobOperation.PICKUP and self.current_cell is not None:
                self.cells[self.current_cell.value].holding_uuid = self.current_job.uuid
            self.current_cell = None
            self.current_job = None
            self.trigger()

    def find_free_cell(self) -> RobotCellLevel:
        """Reserve the first free cell. Raises RuntimeError if all cells are occupied."""
        cell_idx = next((i for i, c in enumerate(self.cells) if c.holding_uuid is None), None)
        if cell_idx is None:
            raise RuntimeError("No free robot cell available for pickup")
        self.current_cell = RobotCellLevel(cell_idx)
        return self.current_cell

    def trigger(self):
        """A function that make the robot works if conditions are met"""
        # Must be active, idle, connected, queue not empty
        is_ready_status = self.last_action_status in (
            RobotActionStatus.IDLE,
            RobotActionStatus.CANCELED,
            RobotActionStatus.SUCCEEDED,
            # RobotActionStatus.ERROR,
            # RobotActionStatus.OPERATING
        )

        if self.active_status and self.connection_status() == RobotConnectionStatus.ONLINE and self.current_job is None and len(self.job_queue) > 0 and is_ready_status:
            self.current_job = self.job_queue.pop(0)
            try:
                if self.current_job.operation == JobOperation.PICKUP:
                    robot_cell = self.find_free_cell()
                else:
                    robot_cell = RobotCellLevel.UNUSED
                self.send_job(self.current_job, robot_cell)
            except RuntimeError:
                self.last_action_status = RobotActionStatus.ERROR
                self.current_job.status = OrderStatus.FAILED
                self.loop.call_soon_threadsafe(self.job_updater.put_nowait, self.current_job)
                self.current_cell = None
                self.current_job = None
    
    def clear_error(self) -> bool:
        if self.last_action_status == RobotActionStatus.ERROR:
            self.last_action_status = RobotActionStatus.IDLE
            self.trigger()
            return True
        return False