from fleet_gateway.api.types import Robot, RobotCell, Job, Request
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

    async def get_robots(self) -> list[Robot]:
        return [connector.toRobot() for connector in self.robot_connector_dict.values()]

    async def get_robot_cells_by_robot(self, robot: Robot) -> list[RobotCell]:
        return self.robot_cells_dict[robot.name]

    async def get_current_job_by_robot(self, robot: Robot) -> Job | None:
        return self.robot_current_job_dict[robot.name]

    async def get_job_queue_by_robot(self, robot: Robot) -> list[Job]:
        return self.robot_job_queue_dict[robot.name]

    # async def get_robot_by_robot_cell(self, robot_cell: RobotCell) -> Robot:
    #     return self.

    # async def get_holding_by_robot_cell(self, cell: RobotCell) -> Request | None:
    #     if cell._holding_uuid is None:
    #         return None
    #     return order_store.get(cell._holding_uuid)