from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio

from fleet_gateway.robot import RobotHandler
from fleet_gateway.route_oracle import RouteOracle

if TYPE_CHECKING:
    from fleet_gateway.api.types import Robot, RobotCell, Job


class FleetHandler():
    """Work as a robot grouper"""
    def __init__(self, job_updater: asyncio.Queue, route_oracle: RouteOracle, robots_config : dict):
        """Initialize all sub-components"""
        self.handlers : dict[str, RobotHandler] = {
            name: RobotHandler(name, cfg["host"], cfg["port"], cfg["cell_heights"], job_updater, route_oracle) 
            for name, cfg in robots_config.items()
        }

    def assign_job(self, robot_name: str, job: Job):
        if robot_name not in self.handlers:
            return
        self.handlers[robot_name].assign(job)

    # API for query
    def get_robot(self, name: str) -> Robot | None:
        if name not in self.handlers:
            return None
        return self.handlers[name].to_robot()

    def get_robots(self) -> list[Robot]:
        return [handler.to_robot() for handler in self.handlers.values()]

    def get_robot_cells(self, name: str) -> list[RobotCell]:
        if name not in self.handlers:
            return []
        return self.handlers[name].cells

    def get_current_job(self, name: str) -> Job | None:
        if name not in self.handlers:
            return None
        return self.handlers[name].current_job

    def get_job_queue(self, name: str) -> list[Job]:
        if name not in self.handlers:
            return []
        return self.handlers[name].job_queue