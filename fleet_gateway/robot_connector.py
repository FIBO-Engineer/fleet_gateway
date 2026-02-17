import asyncio
from fleet_gateway.route_oracle import RouteOracle
from fleet_gateway.helpers.serializers import node_to_dict

from roslibpy import ActionClient, Goal, Ros, Message, Topic

from fleet_gateway.enums import RobotStatus, NodeType
from fleet_gateway.api.types import Robot, Job, Node, MobileBaseState, PiggybackState

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
        self.status = RobotStatus.OFFLINE
        self.mobile_base_state = MobileBaseState()
        self.piggyback_state = PiggybackState()

        # Set up the action client
        self.warehouse_cmd_action_client = ActionClient(self, '/warehouse_command', 'warehouse_server/WarehouseCommandAction')
        self.mobile_base_topic = Topic(self, '/mobile_base/state', 'geometry_msgs/PoseStamped')
        self.mobile_base_topic.subscribe(self.on_mobile_base_update)
        self.piggyback_topic = Topic(self, '/piggyback/state', 'sensor_msgs/JointState')
        self.piggyback_topic.subscribe(self.on_piggyback_update)

        # Setup route oracle
        self.route_oracle: RouteOracle = route_oracle


    def on_mobile_base_update(self, message):
        """Callback for mobile base state updates"""
        # TODO: Fix to actual message type
        if 'pose' in message:
            pose = message['pose']
            self.state.mobile_base_status.x = pose['position']['x']
            self.state.mobile_base_status.y = pose['position']['y']
            # Extract yaw from quaternion
            z = pose['orientation']['z']
            w = pose['orientation']['w']
            self.state.mobile_base_status.a = 2.0 * (w * z)  # Simplified yaw extraction

    def on_piggyback_update(self, message):
        """Callback for piggyback state updates"""
        # TODO: Fix to actual name
        if 'position' in message and len(message['position']) >= 3:
            self.state.piggyback_state.axis_0 = message['position'][0]
            self.state.piggyback_state.axis_1 = message['position'][1]
            self.state.piggyback_state.axis_2 = message['position'][2]

    async def send_job(self, job: Job) -> bool:
        """Send job to robot via ROS action. Use docs/ros_messages/WarehouseCommand.action"""
        """The Job resolve to target node here"""

        if self.mobile_base_state.estimated_tag is None:
            raise RuntimeError("Unable to route its location to the destination due to unknown current location")

        # Known current location
        path_nodes_id : list[int] = self.route_oracle.getShortestPathById(start_id=self.mobile_base_state.estimated_tag.id, end_id=job.target_node)
        path_nodes : list[Node] = self.route_oracle.getNodesByIds(node_ids=path_nodes_id)
        
        goal_msg = Message({
            'nodes': [ node_to_dict(node) for node in path_nodes ],
            'operation': job.operation.value,
            'robot_cell': job.robot_cell
        })

        # Create goal
        goal = Goal(self.warehouse_cmd_action_client, goal_msg)
        self.ros_action_goal = goal
        self.state.current_job = job  # Store full Job object

        # Set robot status to BUSY
        self.state.status = RobotStatus.BUSY

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
                self.state.mobile_base_status.estimated_tag.id = feedback['estimated_tag_id']

        def on_error(error):
            """Handle job error"""
            self.state.current_job = None
            self.ros_action_goal = None
            self.state.status = RobotStatus.ERROR

        goal.send(on_result=on_result, on_feedback=on_feedback, on_error=on_error)
        return True