"""
GraphQL Mutation resolvers for Fleet Gateway.

Handles all write operations: submitting requests and assignments.
"""

import strawberry
import redis.asyncio as redis
import json
from uuid import uuid4

from fleet_gateway import enums
from fleet_gateway.graph_oracle import GraphOracle
from fleet_gateway.fleet_orchestrator import FleetOrchestrator

from .types import RequestInput, AssignmentInput, SubmitResult
from .data_loaders import get_robot_current_node


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

        For each assignment, the system will:
        1. Query graph_oracle to get the shortest path from robot's current position to each target node
        2. Create jobs with the computed paths
        3. Send jobs to the assigned robots

        Args:
            requests: List of warehouse requests (pickup + delivery pairs)
            assignments: List of robot assignments (robot + node IDs to visit)

        Returns:
            SubmitResult with success status, message, and created request UUIDs
        """
        r: redis.Redis = info.context["redis"]
        graph_oracle: GraphOracle = info.context["graph_oracle"]
        graph_id: int = info.context["graph_id"]
        fleet: FleetOrchestrator = info.context["fleet"]

        created_request_uuids = []

        try:
            # Step 1: Create requests in Redis
            request_map = {}  # Map pickup_id to request_uuid
            for req_input in requests:
                request_uuid = str(uuid4())
                created_request_uuids.append(request_uuid)

                # Store pickup_id -> uuid mapping for later
                request_map[req_input.pickup_id] = request_uuid

                # Create placeholder jobs (paths will be computed per robot)
                pickup_job_data = {
                    'operation': enums.WarehouseOperation.PICKUP.value,
                    'nodes': []  # Will be populated when assigned to robot
                }

                delivery_job_data = {
                    'operation': enums.WarehouseOperation.DELIVERY.value,
                    'nodes': []  # Will be populated when assigned to robot
                }

                request_data = {
                    'uuid': request_uuid,
                    'pickup': json.dumps(pickup_job_data),
                    'delivery': json.dumps(delivery_job_data),
                    'handler': '',  # Will be set when assigned
                    'request_status': str(enums.RequestStatus.IN_PROGRESS.value)
                }

                await r.hset(f"request:{request_uuid}", mapping=request_data)
                await r.publish(f"request:{request_uuid}:update", "updated")

            # Step 2: Process assignments
            for assignment in assignments:
                robot_name = assignment.robot
                target_node_ids = assignment.jobs

                # Verify robot exists
                if fleet.get_robot(robot_name) is None:
                    return SubmitResult(
                        success=False,
                        message=f"Robot '{robot_name}' not found",
                        request_uuids=created_request_uuids
                    )

                # Get robot's current position
                current_node_id = await get_robot_current_node(r, robot_name)
                if current_node_id is None:
                    return SubmitResult(
                        success=False,
                        message=f"Robot '{robot_name}' position not found",
                        request_uuids=created_request_uuids
                    )

                # Process each target node
                for target_node_id in target_node_ids:
                    # Determine operation type based on target node
                    # If target is in requests.pickup_id -> PICKUP
                    # If target is in requests.delivery_id -> DELIVERY
                    # Otherwise -> TRAVEL

                    operation = enums.WarehouseOperation.TRAVEL.value
                    request_uuid = None

                    # Check if this is a pickup
                    if target_node_id in request_map:
                        operation = enums.WarehouseOperation.PICKUP.value
                        request_uuid = request_map[target_node_id]

                        # Update request handler
                        await r.hset(f"request:{request_uuid}", 'handler', robot_name)
                        await r.publish(f"request:{request_uuid}:update", "updated")

                    # Check if this is a delivery
                    else:
                        for req_input in requests:
                            if req_input.delivery_id == target_node_id:
                                operation = enums.WarehouseOperation.DELIVERY.value
                                request_uuid = request_map.get(req_input.pickup_id)
                                break

                    # Query graph_oracle for shortest path
                    path_node_ids = graph_oracle.getShortestPathById(
                        graph_id,
                        current_node_id,
                        target_node_id
                    )

                    # Get detailed node information
                    path_nodes = graph_oracle.getNodesByIds(graph_id, path_node_ids)

                    # Convert to dict format for job
                    job_nodes = [
                        {
                            'id': node.id,
                            'alias': node.alias if node.alias else '',
                            'x': node.x,
                            'y': node.y,
                            'height': node.height if node.height else 0.0,
                            'node_type': node.node_type.value if hasattr(node.node_type, 'value') else node.node_type
                        }
                        for node in path_nodes
                    ]

                    # Create and send job
                    job = {
                        'operation': operation,
                        'nodes': job_nodes
                    }

                    # Assign job to robot via orchestrator (handles queuing automatically)
                    await fleet.assign_job(robot_name, job, request_uuid)

                    # Update current position for next path calculation
                    current_node_id = target_node_id

            return SubmitResult(
                success=True,
                message=f"Successfully submitted {len(assignments)} assignments with {len(requests)} requests",
                request_uuids=created_request_uuids
            )

        except Exception as e:
            return SubmitResult(
                success=False,
                message=f"Error: {str(e)}",
                request_uuids=created_request_uuids
            )
