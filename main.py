import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from fleet_gateway.fleet_handler import FleetHandler
from fleet_gateway.order_store import OrderStore
from fleet_gateway.route_oracle import RouteOracle
from fleet_gateway.warehouse_controller import WarehouseController

from fleet_gateway.api.schema import schema

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration loaded from .env
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
GRAPH_ID = int(os.getenv('GRAPH_ID', '1'))
ROBOTS_CONFIG = json.loads(os.getenv('ROBOTS_CONFIG', '{}'))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize RouteOracle (Supabase client)
    try:
        app.state.route_oracle = RouteOracle(SUPABASE_URL, SUPABASE_KEY, GRAPH_ID)
    except Exception as e:
        logger.error("Unable to initialize Supabase client (url=%r): %s", SUPABASE_URL, e)
        raise

    # Initialize Redis connection
    app.state.redis = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True
    )
    try:
        await app.state.redis.ping()
    except Exception as e:
        logger.error("Unable to connect to Redis at %s:%s: %s", REDIS_HOST, REDIS_PORT, e)
        raise

    app.state.job_updater = asyncio.Queue()

    app.state.order_store = OrderStore(app.state.redis)

    app.state.fleet_handler = FleetHandler(app.state.job_updater, app.state.route_oracle, ROBOTS_CONFIG)

    app.state.warehouse_controller = WarehouseController(app.state.job_updater, app.state.fleet_handler, app.state.order_store, app.state.route_oracle)

    try:
        yield
    finally:
        app.state.warehouse_controller._updater_task.cancel()
        await app.state.redis.aclose()

async def get_context(request):
    return {
        "request": request,
        "order_store": request.app.state.order_store,
        "route_oracle": request.app.state.route_oracle,
        "fleet_handler": request.app.state.fleet_handler,
        "warehouse_controller": request.app.state.warehouse_controller,
    }

# Create GraphQL router with context getter
# Note: The schema is already created in fleet_gateway.api.schema
graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(lifespan=lifespan)
app.include_router(graphql_app, prefix="/graphql")
