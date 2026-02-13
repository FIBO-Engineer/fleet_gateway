import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress

import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from fleet_gateway.backup.robot_handler import RobotHandler
from fleet_gateway.route_oracle import RouteOracle
from fleet_gateway.backup.fleet_orchestrator import FleetOrchestrator
from fleet_gateway.api import schema

# Load environment variables
load_dotenv()

# Configuration loaded from .env
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
GRAPH_ID = int(os.getenv('GRAPH_ID', '1'))
ROBOTS_CONFIG = json.loads(os.getenv('ROBOTS_CONFIG', '{}'))

# async def handler_connect_loop(fleet: FleetOrchestrator, stop_event: asyncio.Event):
#     while not stop_event.is_set():
#         for robot_handler in fleet.robots.values():
#             if not robot_handler.is_connected():
#                 robot_handler.connect()

#         # Just delay for 1 second or stop_event is triggered
#         with suppress(asyncio.TimeoutError):
#             await asyncio.wait_for(stop_event.wait(), timeout=1.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize GraphOracle
    app.state.route_oracle = RouteOracle(SUPABASE_URL, SUPABASE_KEY, GRAPH_ID)

    # Initialize Redis connection
    app.state.redis = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True
    )
    await app.state.redis.ping()

    app.state.order_store = OrderStore(app.state.redis)

    app.state.fleet_handler = FleetHandler(app.state.redis, ROBOTS_CONFIG)

    app.state.warehouse_controller = WarehouseController(app.state.order_store, app.state.fleet_handler)

    # Initialize robot handlers from config
    # robot_handlers = [
    #     RobotHandler(
    #         name=robot_name,
    #         host_ip=config['host'],
    #         port=config['port'],
    #         cell_heights=config['cell_heights'],
    #         redis_client=app.state.redis
    #     )
    #     for robot_name, config in ROBOTS_CONFIG.items()
    # ]

    # Initialize robot states in Redis
    # for robot_handler in robot_handlers:
    #     await robot_handler.initialize_in_redis()

    # Create fleet orchestrator (central coordinator)
    # app.state.fleet = FleetOrchestrator(robot_handlers, app.state.redis, app.state.route_oracle)

    stop_event = asyncio.Event()
    # auto_connector = asyncio.create_task(handler_connect_loop(app.state.fleet, stop_event))
    try:
        yield
    finally:
        stop_event.set()
        # await auto_connector
        await app.state.redis.aclose()

async def get_context(request):
    return {
        "request": request,
        "order_store": request.app.state.order_store,
        "route_oracle": request.app.state.route_oracle,
        "fleet_handler": request.app.state.fleet_handler,
    }

# Create GraphQL router with context getter
# Note: The schema is already created in fleet_gateway.api.schema
graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(lifespan=lifespan)
app.include_router(graphql_app, prefix="/graphql")
