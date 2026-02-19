import asyncio
from datetime import datetime, timezone, timedelta

from fleet_gateway.route_oracle import RouteOracle
from fleet_gateway.helpers.serializers import node_to_dict

from roslibpy import ActionClient, Goal, Ros, Message, Topic

from fleet_gateway.enums import RobotConnectionStatus, RobotActionStatus, NodeType
from fleet_gateway.api.types import Robot, Job, Node, MobileBaseState, Pose, Tag, PiggybackState

class RobotConnector(Ros):
    """
    Robot handler that connect to a robot via ROS WarehouseCommand action
    """

    def __init__(self, name: str, host_ip: str, port: int, route_oracle: RouteOracle) -> None:
        super().__init__(host=host_ip, port=port)
        self.run(1.0)

        # Infrastructure (RobotHandler-specific)
        self.ros_action_goal: Goal | None = None

        # Robot state (all operational state in one place)
        self.name = name
        self.action_status = RobotActionStatus.IDLE
        self.mobile_base_state = None
        self.piggyback_state = None

        # Setup the action client
        self.warehouse_cmd_action_client = ActionClient(self, '/warehouse_command', 'warehouse_server/WarehouseCommandAction')
        
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

    def send_job(self, job: Job) -> bool:
        """Send job to robot via ROS action. Use docs/ros_messages/WarehouseCommand.action"""
        """The Job resolve to target node here"""

        if self.mobile_base_state.tag is None:
            raise RuntimeError("Unable to route its location to the destination due to unknown current location")

        # Known current location
        start_node: Node = self.route_oracle.getNodeFromTagId(tag_id=self.mobile_base_state.tag.qr_id)
        path_nodes_id : list[int] = self.route_oracle.getShortestPathById(start_id=start_node.id, end_id=job.target_node.id)
        path_nodes : list[Node] = self.route_oracle.getNodesByIds(node_ids=path_nodes_id)
        # TODO: Continue checking here
        goal_msg = Message({
            'nodes': [ node_to_dict(node) for node in path_nodes ],
            'operation': job.operation.value,
            'robot_cell': job.robot_cell
        })

        # Create goal
        goal = Goal(self.warehouse_cmd_action_client, goal_msg)
        self.ros_action_goal = goal

        # Set robot status to BUSY
        self.action_status = RobotActionStatus.BUSY

        # Send goal with callbacks
        def on_result(result):
            """Handle job completion result"""
            # Update cell holdings based on operation
            from fleet_gateway.enums import JobOperation
            if self.state.current_job.robot_cell >= 0:
                if self.state.current_job.operation == JobOperation.PICKUP:
                    self.allocate_cell(self.state.current_job.robot_cell, self.state.current_job.request_uuid)
                elif self.state.current_job.operation == JobOperation.DELIVERY:
                    self.release_cell(self.state.current_job.robot_cell)

            # Clear current job
            self.state.current_job = None
            self.ros_action_goal = None

            # Set robot status to IDLE
            self.state.status = RobotStatus.IDLE

        def on_feedback(feedback):
            """Handle job feedback"""
            # Update last seen node
            if 'estimated_tag_id' in feedback:
                self.state.mobile_base_state.estimated_tag.id = feedback['estimated_tag_id']

        def on_error(error):
            """Handle job error"""
            self.state.current_job = None
            self.ros_action_goal = None
            self.state.status = RobotStatus.ERROR

        goal.send(on_result=on_result, on_feedback=on_feedback, on_error=on_error)
        return True
    
    def toRobot(self):
        """Convert RobotConnector state to Robot object"""
        return Robot(
            name=self.name,
            connection_status=RobotConnectionStatus(self.is_connected),
            action_status=,
            mobile_base_state=self.mobile_base_state,
            piggyback_state=self.piggyback_state
        )
