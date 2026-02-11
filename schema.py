import strawberry
from uuid import UUID, uuid4
import redis.asyncio as redis
import json
from typing import AsyncGenerator

# Import shared enums and wrap with Strawberry
from fleet_gateway import enums
from fleet_gateway.graph_oracle import GraphOracle
from fleet_gateway.robot_handler import RobotHandler

NodeType = strawberry.enum(enums.NodeType)
RobotStatus = strawberry.enum(enums.RobotStatus)
WarehouseOperation = strawberry.enum(enums.WarehouseOperation)
RequestStatus = strawberry.enum(enums.RequestStatus)

@strawberry.type
class Node:
    id: int
    alias: str | None
    x: float
    y: float
    height: float | None
    node_type: NodeType

@strawberry.type
class MobileBaseState:
    last_seen: Node
    x: float
    y: float
    a: float

@strawberry.type
class PiggybackState:
    axis_0: float
    axis_1: float
    axis_2: float
    gripper: bool

@strawberry.type
class Job:
    operation: WarehouseOperation
    nodes: list[Node]

@strawberry.type
class Robot:
    name: str
    robot_cell_heights: list[float]

    robot_status: RobotStatus
    mobile_base_status: MobileBaseState
    piggyback_state: PiggybackState
    holdings: list["Request"]

    current_job: Job | None
    jobs: list[Job]

@strawberry.type
class Request:
    uuid: UUID
    pickup: Job
    delivery: Job
    handler: Robot | None
    request_status: RequestStatus

# Helper functions to deserialize Redis data
def deserialize_node(data: dict) -> Node:
    return Node(
        id=int(data['id']),
        alias=data.get('alias'),
        x=float(data['x']),
        y=float(data['y']),
        height=float(data['height']) if data.get('height') else None,
        node_type=NodeType(int(data['node_type']))
    )

def deserialize_mobile_base_state(data: dict) -> MobileBaseState:
    return MobileBaseState(
        last_seen=deserialize_node(json.loads(data['last_seen'])),
        x=float(data['x']),
        y=float(data['y']),
        a=float(data['a'])
    )

def deserialize_piggyback_state(data: dict) -> PiggybackState:
    return PiggybackState(
        axis_0=float(data['axis_0']),
        axis_1=float(data['axis_1']),
        axis_2=float(data['axis_2']),
        gripper=data['gripper'].lower() == 'true'
    )

def deserialize_job(data: dict) -> Job:
    return Job(
        operation=WarehouseOperation(int(data['operation'])),
        nodes=[deserialize_node(n) for n in json.loads(data['nodes'])]
    )

def deserialize_robot(data: dict) -> Robot:
    return Robot(
        name=data['name'],
        robot_cell_heights=[float(h) for h in json.loads(data['robot_cell_heights'])],
        robot_status=RobotStatus(int(data['robot_status'])),
        mobile_base_status=deserialize_mobile_base_state(json.loads(data['mobile_base_status'])),
        piggyback_state=deserialize_piggyback_state(json.loads(data['piggyback_state'])),
        holdings=[],  # Will be populated separately if needed
        current_job=deserialize_job(json.loads(data['current_job'])) if data.get('current_job') else None,
        jobs=[deserialize_job(j) for j in json.loads(data['jobs'])] if data.get('jobs') else []
    )

def deserialize_request(data: dict, robot_lookup: dict[str, Robot]) -> Request:
    return Request(
        uuid=UUID(data['uuid']),
        pickup=deserialize_job(json.loads(data['pickup'])),
        delivery=deserialize_job(json.loads(data['delivery'])),
        handler=robot_lookup.get(data['handler']),
        request_status=RequestStatus(int(data['request_status']))
    )

@strawberry.type
class Query:
    @strawberry.field
    async def robots(self, info: strawberry.types.Info) -> list[Robot]:
        r: redis.Redis = info.context["redis"]

        # Pass 1: Deserialize all robots (with empty holdings)
        robot_keys = await r.keys("robot:*")
        robot_lookup = {}

        for key in robot_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    robot = deserialize_robot(data)
                    robot_lookup[robot.name] = robot
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing robot {key}: {e}")
                    continue

        # Pass 2: Deserialize all requests and populate robot holdings
        request_keys = await r.keys("request:*")

        for key in request_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    request = deserialize_request(data, robot_lookup)
                    # Add request to its handler's holdings
                    if request.handler and request.handler.name in robot_lookup:
                        robot_lookup[request.handler.name].holdings.append(request)
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {key}: {e}")
                    continue

        return list(robot_lookup.values())

    @strawberry.field
    async def requests(self, info: strawberry.types.Info) -> list[Request]:
        r: redis.Redis = info.context["redis"]

        # First get all robots for the lookup
        robot_keys = await r.keys("robot:*")
        robot_lookup = {}

        for key in robot_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    robot = deserialize_robot(data)
                    robot_lookup[robot.name] = robot
                except (KeyError, ValueError, json.JSONDecodeError):
                    continue

        # Get all request keys
        request_keys = await r.keys("request:*")
        requests = []

        for key in request_keys:
            data = await r.hgetall(key)
            if data:
                try:
                    requests.append(deserialize_request(data, robot_lookup))
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {key}: {e}")
                    continue

        return requests

    @strawberry.field
    async def robot(self, info: strawberry.types.Info, name: str) -> Robot | None:
        r: redis.Redis = info.context["redis"]
        data = await r.hgetall(f"robot:{name}")

        if not data:
            return None

        try:
            robot = deserialize_robot(data)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Error deserializing robot {name}: {e}")
            return None

        # Populate holdings by finding all requests handled by this robot
        request_keys = await r.keys("request:*")
        robot_lookup = {name: robot}

        for key in request_keys:
            req_data = await r.hgetall(key)
            if req_data and req_data.get('handler') == name:
                try:
                    request = deserialize_request(req_data, robot_lookup)
                    robot.holdings.append(request)
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {key}: {e}")
                    continue

        return robot

    @strawberry.field
    async def request(self, info: strawberry.types.Info, uuid: UUID) -> Request | None:
        r: redis.Redis = info.context["redis"]
        data = await r.hgetall(f"request:{uuid}")

        if not data:
            return None

        # Get robot for the handler
        robot_lookup = {}
        if data.get('handler'):
            robot_data = await r.hgetall(f"robot:{data['handler']}")
            if robot_data:
                try:
                    robot_lookup[data['handler']] = deserialize_robot(robot_data)
                except (KeyError, ValueError, json.JSONDecodeError):
                    pass

        try:
            return deserialize_request(data, robot_lookup)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Error deserializing request {uuid}: {e}")
            return None

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def robot_updates(
        self,
        info: strawberry.types.Info,
        name: str
    ) -> AsyncGenerator[Robot | None, None]:
        """Subscribe to updates for a specific robot by name"""
        r: redis.Redis = info.context["redis"]

        # Create a separate Redis connection for pub/sub
        pubsub = r.pubsub()
        await pubsub.subscribe(f"robot:{name}:update")

        try:
            # Send initial state
            data = await r.hgetall(f"robot:{name}")
            if data:
                try:
                    robot = deserialize_robot(data)

                    # Populate holdings
                    request_keys = await r.keys("request:*")
                    robot_lookup = {name: robot}

                    for key in request_keys:
                        req_data = await r.hgetall(key)
                        if req_data and req_data.get('handler') == name:
                            try:
                                request = deserialize_request(req_data, robot_lookup)
                                robot.holdings.append(request)
                            except (KeyError, ValueError, json.JSONDecodeError):
                                continue

                    yield robot
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing robot {name}: {e}")
                    yield None
            else:
                yield None

            # Listen for updates
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Fetch updated robot data
                    data = await r.hgetall(f"robot:{name}")
                    if data:
                        try:
                            robot = deserialize_robot(data)

                            # Populate holdings
                            request_keys = await r.keys("request:*")
                            robot_lookup = {name: robot}

                            for key in request_keys:
                                req_data = await r.hgetall(key)
                                if req_data and req_data.get('handler') == name:
                                    try:
                                        request = deserialize_request(req_data, robot_lookup)
                                        robot.holdings.append(request)
                                    except (KeyError, ValueError, json.JSONDecodeError):
                                        continue

                            yield robot
                        except (KeyError, ValueError, json.JSONDecodeError) as e:
                            print(f"Error deserializing robot {name}: {e}")
                            yield None
        finally:
            await pubsub.unsubscribe(f"robot:{name}:update")
            await pubsub.close()

    @strawberry.subscription
    async def request_updates(
        self,
        info: strawberry.types.Info,
        uuid: UUID
    ) -> AsyncGenerator[Request | None, None]:
        """Subscribe to updates for a specific request by UUID"""
        r: redis.Redis = info.context["redis"]

        # Create a separate Redis connection for pub/sub
        pubsub = r.pubsub()
        await pubsub.subscribe(f"request:{uuid}:update")

        try:
            # Send initial state
            data = await r.hgetall(f"request:{uuid}")
            if data:
                # Get robot for the handler
                robot_lookup = {}
                if data.get('handler'):
                    robot_data = await r.hgetall(f"robot:{data['handler']}")
                    if robot_data:
                        try:
                            robot_lookup[data['handler']] = deserialize_robot(robot_data)
                        except (KeyError, ValueError, json.JSONDecodeError):
                            pass

                try:
                    yield deserialize_request(data, robot_lookup)
                except (KeyError, ValueError, json.JSONDecodeError) as e:
                    print(f"Error deserializing request {uuid}: {e}")
                    yield None
            else:
                yield None

            # Listen for updates
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Fetch updated request data
                    data = await r.hgetall(f"request:{uuid}")
                    if data:
                        # Get robot for the handler
                        robot_lookup = {}
                        if data.get('handler'):
                            robot_data = await r.hgetall(f"robot:{data['handler']}")
                            if robot_data:
                                try:
                                    robot_lookup[data['handler']] = deserialize_robot(robot_data)
                                except (KeyError, ValueError, json.JSONDecodeError):
                                    pass

                        try:
                            yield deserialize_request(data, robot_lookup)
                        except (KeyError, ValueError, json.JSONDecodeError) as e:
                            print(f"Error deserializing request {uuid}: {e}")
                            yield None
        finally:
            await pubsub.unsubscribe(f"request:{uuid}:update")
            await pubsub.close()

# Input types for mutations
@strawberry.input
class RequestInput:
    """Input for a warehouse request (pickup + delivery pair)"""
    pickup_id: int  # Node ID of the shelf to pick from
    delivery_id: int  # Node ID of the depot to deliver to

@strawberry.input
class AssignmentInput:
    """Input for a robot assignment"""
    robot: str  # Name of the robot
    jobs: list[int]  # List of node IDs to visit in order

@strawberry.type
class SubmitResult:
    """Result of submitting requests and assignments"""
    success: bool
    message: str
    request_uuids: list[str]  # UUIDs of created requests

@strawberry.type
class Mutation:
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
        """
        r: redis.Redis = info.context["redis"]
        graph_oracle: GraphOracle = info.context["graph_oracle"]
        graph_id: int = info.context["graph_id"]
        robot_lookup: dict[str, RobotHandler] = info.context["robot_lookup"]

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

                # Get robot handler
                robot_handler = robot_lookup.get(robot_name)
                if not robot_handler:
                    return SubmitResult(
                        success=False,
                        message=f"Robot '{robot_name}' not found",
                        request_uuids=created_request_uuids
                    )

                # Get robot's current position
                robot_data = await r.hgetall(f"robot:{robot_name}")
                if not robot_data:
                    return SubmitResult(
                        success=False,
                        message=f"Robot '{robot_name}' state not found in Redis",
                        request_uuids=created_request_uuids
                    )

                mobile_base_status = json.loads(robot_data['mobile_base_status'])
                current_node_id = mobile_base_status['last_seen']['id']

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

                    if request_uuid:
                        job['request_uuid'] = request_uuid

                    # Send job to robot (or queue if busy)
                    if robot_handler.current_job is None:
                        await robot_handler.send_job(job, request_uuid)
                    else:
                        robot_handler.job_queue.append(job)

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
