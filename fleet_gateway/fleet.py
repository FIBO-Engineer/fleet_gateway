from typing import Dict, Any, List
from fleet_gateway.robot_handler import Robot


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
