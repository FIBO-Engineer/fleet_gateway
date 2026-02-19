from fleet_gateway.api.types import Robot, RobotCell, Job
from fleet_gateway.robot_connector import RobotConnector
from fleet_gateway.route_oracle import RouteOracle
import strawberry

class FleetHandler():
    def __init__(self, route_oracle: RouteOracle, robots_config : dict):
        """Initialize all sub-components"""
        self.robot_connector_dict : dict[str, RobotConnector] = {
            name : RobotConnector(name, cfg["host"], cfg["port"], route_oracle) for name, cfg in robots_config.items()
        }

        self.robot_cells_dict: dict[str, list[RobotCell]] = {
            name: [RobotCell(height) for height in cfg.cell_heights] for name, cfg in robots_config.items()
        }

        self.robot_current_job_dict: dict[str, Job | None] = {}
        self.robot_job_queue_dict: dict[str, list[Job]] = {}

    def get_robot(self, name: str) -> Robot | None:
        return self.robot_connector_dict[name].toRobot()

    def get_robots(self) -> list[Robot]:
        return [connector.toRobot() for connector in self.robot_connector_dict.values()]

    def get_robot_cells(self, name: str) -> list[RobotCell]:
        return self.robot_cells_dict[name]

    def get_current_job(self, name: str) -> Job | None:
        return self.robot_current_job_dict[name]

    def get_job_queue(self, name: str) -> list[Job]:
        return self.robot_job_queue_dict[name]