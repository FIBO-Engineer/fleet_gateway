import redis.asyncio as redis

from fleet_gateway.api.types import Robot, RobotCell, Job, Request

class FleetHandler():
    def __init__(self, redis_client: redis.Redis, robots_config : dict):
        """Initialize OrderStore with Redis client"""
        # self.redis = redis_client
        robots_config[" "]

    async def get_robot(self, name: str) -> Robot | None:
        status = await self.redis.hgetall(f"robot:{name}", "status")

        if status is None:
            return None

        return Request(
            uuid=UUID(uuid),
            status=RequestStatus(int(status)),
        )

    async def get_robots(self) -> list[Robot]:
        raise NotImplementedError

    async def get_robot_cells_by_robot(self, root: Robot) -> list[RobotCell]:
        raise NotImplementedError

    async def get_current_job_by_robot(self, root: Robot) -> Job | None:
        raise NotImplementedError

    async def get_job_queue_by_robot(self, root: Robot) -> list[Job]:
        raise NotImplementedError

    async def get_robot_by_robot_cell(self, root: RobotCell) -> Robot:
        raise NotImplementedError

    async def get_holding_by_robot_cell(self, root: RobotCell) -> Request | None:
        raise NotImplementedError