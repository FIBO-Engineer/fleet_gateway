"""
GraphQL Mutation resolvers for Fleet Gateway.

Handles all write operations: submitting requests and assignments.
"""

import strawberry

from fleet_gateway.graph_oracle import GraphOracle
from fleet_gateway.fleet_orchestrator import FleetOrchestrator

from .types import RequestInput, AssignmentInput, SubmitResult


@strawberry.type
class Mutation:
    """GraphQL Mutation root"""

    @strawberry.mutation
    async def submit_assignments(
        self,
        info: strawberry.types.Info,
        requests: list[RequestInput],
        assignments: list[AssignmentInput]
    ) -> SubmitResult:
        """
        Submit warehouse requests and robot assignments.

        This is a thin wrapper around FleetOrchestrator.submit_requests_and_assignments().
        All business logic and Redis operations are handled by the orchestrator.

        Args:
            requests: List of warehouse requests (pickup + delivery pairs)
            assignments: List of robot assignments (robot + node IDs to visit)

        Returns:
            SubmitResult with success status, message, and created request UUIDs
        """
        graph_oracle: GraphOracle = info.context["graph_oracle"]
        graph_id: int = info.context["graph_id"]
        fleet: FleetOrchestrator = info.context["fleet"]

        try:
            # Delegate all business logic to orchestrator
            request_uuids = await fleet.submit_requests_and_assignments(
                requests=requests,
                assignments=assignments,
                graph_oracle=graph_oracle,
                graph_id=graph_id
            )

            return SubmitResult(
                success=True,
                message=f"Successfully submitted {len(assignments)} assignments with {len(requests)} requests",
                request_uuids=request_uuids
            )

        except (ValueError, RuntimeError) as e:
            # Business logic errors from orchestrator
            return SubmitResult(
                success=False,
                message=f"Error: {str(e)}",
                request_uuids=[]
            )

        except Exception as e:
            # Unexpected errors
            return SubmitResult(
                success=False,
                message=f"Unexpected error: {str(e)}",
                request_uuids=[]
            )
