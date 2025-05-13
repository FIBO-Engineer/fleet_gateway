import time
import math

import signal
import sys
import termios
import tty
import select

import roslibpy
import roslibpy.actionlib

import networkx as nx
from typing import Sequence, Dict, Any, List, Optional

class Robot(roslibpy.Ros):
    def __init__(self, name: str, host_ip: str, port: int) -> None:
        super().__init__(host=host_ip, port=port)
        self.run(1.0)
        self.name = name
        self.reached = True
        # set up the action client and wait for server
        self.move_base_action_client = roslibpy.actionlib.ActionClient(
            self,
            '/move_base',
            'move_base_msgs/MoveBaseAction'
        )
        # if self.move_base_action_client.wait_for_server(timeout=5.0):
        #     print(f"{self.name}: action server ready")
        # else:
        #     print(f"{self.name}: no action server")
        self.goal: Optional[roslibpy.actionlib.Goal] = None

    def navigate(self, pose: dict, frame_id: str = 'map') -> None:
        """
        pose should be a dict:
        {
            'position':    {'x': x, 'y': y, 'z': 0.0},
            'orientation': {'x': ox, 'y': oy, 'z': oz, 'w': ow}
        }
        """
        if self.goal is not None and not self.reached:
            self.goal.cancel()

        # mark in-flight
        self.reached = False

        # Construct a PoseStamped inside a MoveBaseGoal
        goal_msg = roslibpy.Message({
            'target_pose': {
                'header': {
                    'stamp': {'secs': 0, 'nsecs': 0},
                    'frame_id': frame_id
                },
                'pose': pose
            }
        })

        self.goal = roslibpy.actionlib.Goal(self.move_base_action_client, goal_msg)

        # when the action returns a result, mark as reached
        def _on_result(result):
            # result is a MoveBaseResult message
            self.reached = True
            print(f"{self.name}: navigation complete → {result}")
            # self.move_base_action_client.dispose() # Don't

        self.goal.on('result', _on_result)
        self.goal.send()
    
    def cancel(self) -> None:
        if self.goal is not None and not self.reached:
            self.goal.cancel()
            self.reached = True
        else:
            raise RuntimeError("No goal to cancel")
        
    
    def has_reached(self) -> bool:
        return self.reached
        

class Fleet(List[Robot]):
    def __init__(self, *robots):
        super().__init__(robots)

    def terminate(self):
        for robot in self:
            robot.terminate()

    # def connect(self):
    #     for robot in self:
    #         try:
    #             print(robot.name + ' successfully joined to the fleet')
    #         except roslibpy.core.RosTimeoutError:
    #             print(robot.name + ' failed to joined to the fleet')   

    def send_targets(self, poses: Dict[str, Any]):
        for robot in self:
            if robot.name in poses:
                robot.navigate(poses[robot.name])
            else:
                print('Warning: ' + robot.name + ' has no target')

    def cancel_all(self):
        for robot in self:
            robot.cancel()

    def all_reached(self):
        return all(robot.has_reached() for robot in self)
    
    # def print_status(self):
    #     for robot in self:
    #         status = 'connected' if robot.is_connected else 'disconnected'
    #         print(f"{robot.name} {status}")

    def print_status(self):
        for robot in self:
            print(f"{robot.name} {robot.reached} ")

class PathNetwork(nx.DiGraph):
    def __init__(self, poses: Sequence[Any]) -> None:
        """Create a directed cycle; node i gets pose poses[i]."""
        super().__init__()
        for i, pose in enumerate(poses):
            self.add_node(i, pose=pose)
        n = len(poses)
        for i in range(n):
            self.add_edge(i, (i + 1) % n)

    def place_robot(self, node: int, name: str) -> None:
        """Place a robot at a specific node."""
        if node not in self:
            raise KeyError(f"Node {node} doesn’t exist")
        self.nodes[node]['robot'] = name

    def step_robots(self) -> Dict[str, Any]:
        """Advance each robot one step along the directed cycle."""
        positions = [
            (node, data['robot'])
            for node, data in self.nodes(data=True)
            if 'robot' in data
        ]
        for node, _ in positions:
            self.nodes[node].pop('robot', None)

        for node, name in positions:
            succs = list(self.successors(node))
            if succs:
                self.nodes[succs[0]]['robot'] = name
        
        return self.current_robot_poses()

    def current_robot_poses(self) -> Dict[str, Any]:
        """Return mapping robot_name → current pose."""
        poses: Dict[str, Any] = {}
        for data in self.nodes.values():
            name = data.get('robot')
            if name is not None:
                poses[name] = data['pose']
        return poses


def pose_msg(x, y, yaw): 
    return {
        'position': {'x': x, 'y': y, 'z': 0.0},
        'orientation': {'x': 0.0, 'y': 0.0, 'z': math.sin(yaw/2), 'w': math.cos(yaw/2)}
    }

[
  { "x": 9.31, "y": 6.33 },
  { "x": 9.86, "y": 7.29 },
  { "x": 10.41, "y": 8.24 },
  { "x": 10.96, "y": 7.29 },
  { "x": 11.51, "y": 6.33 },
  { "x": 10.41, "y": 6.33 }
]


robot_network = PathNetwork([
    pose_msg(9.31, 6.33, -1.57),
    pose_msg(9.86, 7.29, -1.57),
    pose_msg(10.41, 8.24, -1.57),
    pose_msg(10.96, 7.29, -1.57),
    pose_msg(11.51, 6.33, -1.57),
    pose_msg(10.41, 6.33, -1.57)
])

# Robot Initials
# robot_network.place_robot(0, 'Journey')
robot_network.place_robot(2, 'Somshine')
robot_network.place_robot(4, 'Chompu')

# Connection Configuration
# journey = Robot('Journey', '192.168.123.151', 8002)
chompu = Robot('Chompu', '192.168.123.171', 8002)
somshine = Robot('Somshine', '192.168.123.172', 8002)
# fleet = Fleet(journey, chompu, somshine)
fleet = Fleet(chompu, somshine)


# Define a clean shutdown on Ctrl+C
def signal_handler(sig, frame):
    print('Interrupt received, shutting down')
    fleet.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Configure terminal to read single key without blocking
fd = sys.stdin.fileno()
old_term_settings = termios.tcgetattr(fd)
tty.setcbreak(fd)

progressing = False
automatic = False

try:
    while any(robot.is_connected for robot in fleet):
        # Check for 'q' key press to quit
        dr, dw, de = select.select([sys.stdin], [], [], 0)
        if dr:
            ch = sys.stdin.read(1)
            if ch == 'q':
                print("Key 'q' pressed, exiting loop")
                break
            elif ch == 'a':
                automatic = not automatic
                print(f"Key 'a' pressed, toggle automatic mode to: {automatic}")
                if automatic and not progressing:
                    fleet.send_targets(robot_network.step_robots())
                    progressing = True
                continue
            elif ch == 's':
                if progressing:
                    print("Key 's' pressed, do nothing because fleet is already in progress")
                else:
                    print("Key 's' pressed, sending a step command to next position")
                    fleet.send_targets(robot_network.step_robots())
                    progressing = True
                continue
            elif ch == 'c':
                print("Key 'c' pressed, cancel command issued")
                progressing = False
                fleet.cancel_all()
                continue
            elif ch == 'g':
                print("Key 'g' pressed, get status")
                fleet.print_status()
                continue
        
        if progressing and fleet.all_reached():
            if automatic:
                fleet.send_targets(robot_network.step_robots())
            else:
                progressing = False

        time.sleep(1)
except KeyboardInterrupt:
    print('Shutting down gracefully')
finally:
    # Restore terminal settings
    termios.tcsetattr(fd, termios.TCSADRAIN, old_term_settings)
    # talker.unadvertise()
    fleet.terminate()