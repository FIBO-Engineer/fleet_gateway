from fleet_gateway.api.types import Robot, RobotCell, Job
from fleet_gateway.robot import RobotHandler
from fleet_gateway.route_oracle import RouteOracle

import asyncio

class FleetHandler():
    """Work as a robot grouper"""
    def __init__(self, async_queue: asyncio.Queue, route_oracle: RouteOracle, robots_config : dict):
        """Initialize all sub-components"""
        self.handlers : dict[str, RobotHandler] = {
            name: RobotHandler(name, cfg["host"], cfg["port"], cfg["cell_heights"], async_queue, route_oracle) 
            for name, cfg in robots_config.items()
        }

    def assign_job(self, robot_name: str, job: Job):
        self.handlers[robot_name].assign(job)

    # API for query
    def get_robot(self, name: str) -> Robot | None:
        return self.handlers[name].to_robot()

    def get_robots(self) -> list[Robot]:
        return [handler.to_robot() for handler in self.handlers.values()]

    def get_robot_cells(self, name: str) -> list[RobotCell]:
        return self.handlers[name].cells

    def get_current_job(self, name: str) -> Job | None:
        return self.handlers[name].current_job

    def get_job_queue(self, name: str) -> list[Job]:
        return self.handlers[name].job_queue