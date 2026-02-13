"""
Combined GraphQL schema for Fleet Gateway.

This module combines all GraphQL components (queries, mutations, subscriptions)
into a single Strawberry schema for use with FastAPI.
"""

import strawberry
from uuid import UUID

from fleet_gateway.api.types import Robot, Request, RequestInput, AssignmentInput, OrderResult
import fleet_gateway.api.resolvers as resolvers

@strawberry.type
class Query:

    @strawberry.field
    async def robots(self, info: strawberry.types.Info) -> list[Robot]:
        return resolvers.get_robots(info)

    @strawberry.field
    async def requests(self, info: strawberry.types.Info) -> list[Request]:
        return resolvers.get_requests(info)

    @strawberry.field
    async def robot(self, info: strawberry.types.Info, name: str) -> Robot | None:
        return resolvers.get_robot_by_name(info, name)

    @strawberry.field
    async def request(self, info: strawberry.types.Info, uuid: UUID) -> Request | None:
        return resolvers.get_request_by_uuid(info, uuid)

@strawberry.type
class Mutation:
    """All mutations go to warehouse_controller"""

    @strawberry.mutation
    async def send_robot_order(self, info: strawberry.types.Info, request: RequestInput, robot_name: str) -> OrderResult:
        """Submit warehouse requests and robot assignments. """
        return resolvers.send_robot_order(info, request, robot_name)

    @strawberry.mutation
    async def send_fleet_order(self, info: strawberry.types.Info, requests: list[RequestInput], assignments: list[AssignmentInput]) -> OrderResult:
        """Submit warehouse requests and robot assignments. """
        return resolvers.send_fleet_order(info, requests, assignments)

    @strawberry.mutation
    async def activate(self, info: strawberry.types.Info, robot_name: str, enable: bool) -> Robot:
        """Allowing the robot to take the command from queue"""
        return resolvers.activate_robot(info, robot_name, enable)

    @strawberry.mutation
    async def cancel_request(self, info: strawberry.types.Info, request_uuid: UUID) -> UUID:
        return resolvers.cancel_request(info, request_uuid)
    
    # @strawberry.mutation
    # async def set_cell_occupied(self, info: strawberry.types.Info, request_uuid: UUID) -> UUID:
    #     return resolvers.send_order(info.context["warehouse_controller"], request_uuid)
    
    # @strawberry.mutation
    # async def set_cell_free(self, info: strawberry.types.Info, request_uuid: UUID) -> UUID:
    #     return resolvers.send_order(info.context["warehouse_controller"], request_uuid)
    

# Create the combined GraphQL schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
)
