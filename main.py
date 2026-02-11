import asyncio
import os
from contextlib import asynccontextmanager, suppress

import redis.asyncio as redis
import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from fleet_gateway.robot_handler import RobotHandler
from fleet_gateway.graph_oracle import GraphOracle
from schema import Query, Subscription, Mutation

async def handler_connect_loop(robot_handlers: list[RobotHandler], stop_event: asyncio.Event):
    while not stop_event.is_set():
        for rh in robot_handlers:
            if not rh.is_connected():
                rh.connect()

        # Just delay for 1 second or stop_event is triggered
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Redis connection
    app.state.redis = redis.Redis(host='localhost', port=6379, decode_responses=True)
    await app.state.redis.ping()

    # Initialize GraphOracle
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    app.state.graph_oracle = GraphOracle(supabase_url, supabase_key)
    app.state.graph_id = int(os.environ.get("GRAPH_ID", "1"))  # Default graph ID

    # Initialize robot handlers with Redis client
    app.state.robot_handlers = [
        RobotHandler(
            name='Lertvilai',
            host_ip='192.168.123.171',
            port=8002,
            cell_heights=[0.5, 1.0, 1.5],  # Example heights in meters
            redis_client=app.state.redis
        ),
        # RobotHandler(
        #     name='Chompu',
        #     host_ip='192.168.123.171',
        #     port=8003,
        #     cell_heights=[0.5, 1.0, 1.5],
        #     redis_client=app.state.redis
        # )
    ]

    # Create robot lookup dict
    app.state.robot_lookup = {rh.name: rh for rh in app.state.robot_handlers}

    # Initialize robot states in Redis
    for robot_handler in app.state.robot_handlers:
        await robot_handler.initialize_in_redis()

    stop_event = asyncio.Event()
    auto_connector = asyncio.create_task(handler_connect_loop(app.state.robot_handlers, stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await auto_connector
        await app.state.redis.aclose()

async def get_context(request):
    return {
        "request": request,
        "redis": request.app.state.redis,
        "graph_oracle": request.app.state.graph_oracle,
        "graph_id": request.app.state.graph_id,
        "robot_lookup": request.app.state.robot_lookup,
    }

schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription, context_getter=get_context)
graphql_app = GraphQLRouter(schema)

app = FastAPI(lifespan=lifespan)
app.include_router(graphql_app, prefix="/graphql")
