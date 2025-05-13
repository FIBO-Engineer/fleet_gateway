import time

import signal
import sys
import termios
import tty
import select

import roslibpy
import roslibpy.actionlib

import networkx as nx

class Robot(roslibpy.Ros):
    def __init__(self, name, host_ip, port):
        super().__init__(host=host_ip, port=port)
        self.name = name
    def setup_action_client(self):
        self.move_base_action_client = roslibpy.actionlib.ActionClient(self, 
                                                '/move_base',
                                                'move_base_msgs/MoveBase')

class Fleet(list):
    def __init__(self, *robots):
        super().__init__(robots)

    def terminate(self):
        for robot in self:
            robot.terminate()

    def run(self):
        for robot in self:
            try:
                robot.run(1.0)
                print(robot.name + ' sucessfully joined to the fleet')
            except roslibpy.core.RosTimeoutError:
                print(robot.name + ' failed to joined to the fleet')

    def print_connection_status(self):
        for robot in self:
            status = 'connected' if robot.is_connected else 'disconnected'
            print(f"{robot.name} {status}")

    def notify_move_base_feedback(self):
        pass

        
# Fleet Configuration
journey = Robot('Journey', '192.168.123.151', 8002)
chompu = Robot('Chompu', '192.168.123.171', 8002)
somshine = Robot('Somshine', '192.168.123.172', 8002)
fleet = Fleet(journey, chompu, somshine)
fleet.run()


class PathNetwork(nx.DiGraph):
    def __init__(self):
        super().__init__()
        self.add_nodes_from([
            (0, {"robot": "journey", }),
            (1, {}),
            (2, {"robot": "somshine"}),
            (3, {}),
            (4, {"robot": "chompu"}), 
            (5, {})
        ])
        for i in range(6):
            self.add_edge(i, (i + 1) % 6)

    def progress_robot(self):
        # 1) Collect all robots and their current nodes
        robot_positions = [
            (n, data['robot'])
            for n, data in self.nodes(data=True)
            if 'robot' in data
        ]

        # 2) Remove 'robot' attribute from their old nodes
        for n, _ in robot_positions:
            self.nodes[n].pop('robot', None)

        # 3) Move each robot to its successor node
        for n, robot in robot_positions:
            # since this is a simple cycle, each node has exactly one successor
            next_node = next(self.successors(n))
            self.nodes[next_node]['robot'] = robot
    
    def get_goals(self):
        #

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

auto = False

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
                auto = not auto
                print("Auto run: " + auto)
                break
            elif ch == 's':
                print("Step")
                

        # fleet.print_connection_status()
        # Main code
        if auto:
            



        time.sleep(1)
except KeyboardInterrupt:
    print('Shutting down gracefully')
finally:
    # Restore terminal settings
    termios.tcsetattr(fd, termios.TCSADRAIN, old_term_settings)
    # talker.unadvertise()
    fleet.terminate()