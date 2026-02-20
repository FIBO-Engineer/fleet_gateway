from fleet_gateway.api.types import Robot, RobotCell, Job
from fleet_gateway.robot import RobotHandler
from fleet_gateway.route_oracle import RouteOracle

class FleetHandler():
    def __init__(self, route_oracle: RouteOracle, robots_config : dict):
        """Initialize all sub-components"""
        self.handlers : dict[str, RobotHandler] = {
            name: RobotHandler(name, cfg["host"], cfg["port"], cfg["cell_heights"], route_oracle) 
            for name, cfg in robots_config.items()
        }

    def assign_job(self, robot_name: str, job: Job):
        ...

    # API for query
    def get_robot(self, name: str) -> Robot | None:
        return self.handlers[name].toRobot()

    def get_robots(self) -> list[Robot]:
        return [handler.toRobot() for handler in self.handlers.values()]

    def get_robot_cells(self, name: str) -> list[RobotCell]:
        return self.handlers[name].cells

    def get_current_job(self, name: str) -> Job | None:
        return self.handlers[name].current_job

    def get_job_queue(self, name: str) -> list[Job]:
        return self.handlers[name].job_queue