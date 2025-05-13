import time

import signal
import sys
import termios
import tty
import select

import roslibpy

class Robot(roslibpy.Ros):
    def __init__(self, name, host_ip, port):
        super(Robot, self, host_ip, port).__init__()
        self.name = name

class Fleet(list):
    def terminate(self):
        for robot in self:
            robot.terminate()
    def print_connection_status(self):
        for robot in self:
            status = 'connected' if robot.is_connected() else 'disconnected'
            print(f"{robot.name} {status}")
        
journey = roslibpy.Ros('Journey', '192.168.123.151', 8002)
chompu = roslibpy.Ros('Chompu', '192.168.123.171', 8002)
somshine = roslibpy.Ros('Somshine', '192.168.123.172', 8002)

fleet = Fleet(journey, chompu, somshine)

# Define a clean shutdown on Ctrl+C
def signal_handler(sig, frame):
    print('Interrupt received, shutting down')
    fleet.terminate
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Configure terminal to read single key without blocking
fd = sys.stdin.fileno()
old_term_settings = termios.tcgetattr(fd)
tty.setcbreak(fd)

try:
    while any(robot.is_connected() for robot in fleet):
        # Check for 'q' key press to quit
        dr, dw, de = select.select([sys.stdin], [], [], 0)
        if dr:
            ch = sys.stdin.read(1)
            if ch == 'q':
                print("Key 'q' pressed, exiting loop")
                break
        fleet.print_connection_status()
        time.sleep(1)
except KeyboardInterrupt:
    print('Shutting down gracefully')
finally:
    # Restore terminal settings
    termios.tcsetattr(fd, termios.TCSADRAIN, old_term_settings)
    # talker.unadvertise()
    fleet.terminate()