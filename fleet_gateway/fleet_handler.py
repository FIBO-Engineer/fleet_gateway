from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio
from uuid import UUID

from fleet_gateway.robot import RobotHandler
from fleet_gateway.route_oracle import RouteOracle

if TYPE_CHECKING:
    from fleet_gateway.api.types import Robot, RobotCell, Job, RobotCellInput


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

    def remove_queued_job(self, robot_name: str, job_uuid: UUID) -> bool:
        if robot_name not in self.handlers:
            return False
        queue = self.handlers[robot_name].job_queue
        for i, job in enumerate(queue):
            if job.uuid == job_uuid:
                queue.pop(i)
                return True
        return False

    def shutdown(self):
        """Stop reconnect loops and close all robot WebSocket connections."""
        for handler in self.handlers.values():
            handler.shutdown()
        if self.handlers:
            # The Twisted reactor is shared; terminate it via any handler instance
            next(iter(self.handlers.values())).terminate()

    async def free_cell(self, robot_cell: RobotCellInput) -> RobotCell | None:
        if robot_cell.robot_name not in self.handlers:
            return None
        handler = self.handlers[robot_cell.robot_name]
        if robot_cell.cell_index < 0 or robot_cell.cell_index >= len(handler.cells):
            return None
        cell = handler.cells[robot_cell.cell_index]
        cell.holding_uuid = None
        return cell