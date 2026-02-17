from uuid import UUID
from fleet_gateway.api.types import OrderResult, Robot

class WarehouseController():
    async def send_robot_order(self) -> OrderResult:
        raise NotImplementedError

    async def send_fleet_order(self) -> OrderResult:
        raise NotImplementedError

    async def activate(self, robot_name: str, enable: bool) -> Robot:
        raise NotImplementedError

    async def cancel(self, request_uuid: UUID) -> UUID:
        raise NotImplementedError
