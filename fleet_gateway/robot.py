import asyncio
from datetime import datetime, timezone, timedelta

from fleet_gateway.route_oracle import RouteOracle
from fleet_gateway.helpers.serializers import node_to_dict

from roslibpy import ActionClient, Goal, GoalStatus, Ros, Topic

from fleet_gateway.enums import RobotConnectionStatus, RobotActionStatus
from fleet_gateway.api.types import Robot, RobotCell, Job, Node, MobileBaseState, Pose, Tag, PiggybackState

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
        self.mobile_base_state = None
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
            orientation = message['pose']['orientation']
            a = 2.0 * (orientation['w'] * orientation['z'])  # Simplified yaw extraction
            pose = Pose(datetime.now(timezone(timedelta(hours=7))), message['pose']['x'], message['pose']['y'], a)
            if self.mobile_base_state is None:
                self.mobile_base_state = MobileBaseState(None, pose)
            else:
                self.mobile_base_state.pose = pose
    
    def qr_id_callback(self, message):
        """"Callback for QR"""
        if 'data' in message:
            tag = Tag(datetime.now(timezone(timedelta(hours=7))), message['data'])
            if self.mobile_base_state is None:
                self.mobile_base_state = MobileBaseState(tag, None)
            else:
                self.mobile_base_state.tag = tag

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
            except ValueError:
                pass

    def send_job(self, job: Job):
        """Send job to robot via ROS action. Use docs/ros_messages/WarehouseCommand.action"""
        """The Job resolve to target node here"""

        if self.mobile_base_state.tag is None:
            raise RuntimeError("Unable to route its location to the destination due to unknown current location")

        # Known current location
        start_node: Node | None = self.route_oracle.getNodeByTagId(tag_id=self.mobile_base_state.tag.qr_id)
        if start_node is None:
            raise RuntimeError("Unable to query start_node")
        
        path_node_ids : list[int] = self.route_oracle.getShortestPathById(start_id=start_node.id, end_id=job.target_node.id)
        path_nodes : list[Node] = self.route_oracle.getNodesByIds(node_ids=path_node_ids)
        
        goal = Goal({
            'nodes': [ node_to_dict(node) for node in path_nodes ],
            'operation': job.operation.value,
            'robot_cell': job.robot_cell
        })

        # Send goal with callbacks
        def on_result(result):
            """Handle job completion result"""
            match result["status"]:
                case GoalStatus.SUCCEEDED:
                    self.last_action_status = RobotActionStatus.IDLE
                case GoalStatus.CANCELED:
                    self.last_action_status = RobotActionStatus.CANCELED
                case GoalStatus.ABORTED:
                    self.last_action_status = RobotActionStatus.ERROR
                case _:
                    raise RuntimeError("Unexpected case on_result")
            # Set Job status
            
            
            # self.action_future.set_result(result)

        def on_feedback(feedback):
            """Handle job feedback"""
            pass

        def on_error(error):
            """Handle job error"""
            print(f"{self.name} error")
            # self.action_future.set_exception(error)

        self.warehouse_cmd_action_client.send_goal(goal, on_result, on_feedback, on_error)
        self.last_action_status = RobotActionStatus.OPERATING
        
        # self.action_future = asyncio.Future[GoalStatus] = asyncio.get_running_loop().create_future()

        return self.action_future
    
    def notify_job_completion(self):
        pass
    
    def to_robot(self):
        """Convert RobotConnector state to Robot object"""
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
    def __init__(self, name: str, host_ip: str, port: int, cell_heights: list[float], async_queue: asyncio.Queue, route_oracle: RouteOracle):
        super().__init__(name, host_ip, port, route_oracle)
        self.cells : list[RobotCell] = [RobotCell(height) for height in cell_heights]
        self.current_job : Job | None = None
        self.job_queue : list[Job] = []
        self.async_queue = async_queue
    
    def assign(self, job: Job):
        self.job_queue.append(job)
        self.trigger_job()
    
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

        if self.active_status and self.connection_status() and self.current_job is None and self.job_queue.count() > 0 and is_ready_status:
            self.current_job = self.job_queue.pop(0)
            self.send_job(self.current_job)
            
    def notify_job_completion(self):
        self.async_queue.put_nowait(self.job_queue)

    def clear_error(self) -> bool:
        if RobotActionStatus.ERROR:
            self.last_action_status = RobotActionStatus.IDLE
            return True
        return False