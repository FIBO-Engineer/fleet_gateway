import asyncio
from contextlib import asynccontextmanager, suppress

import redis.asyncio as redis
import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from fleet_gateway.robot_handler import RobotHandler
from schema import Query

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
    app.state.robot_handlers = [
        RobotHandler('Lertvilai', '192.168.123.171', 8002),
        # RobotHandler('Chompu', '192.168.123.171', 8002)
    ]
    app.state.redis = redis.Redis(host='localhost', port=6379, decode_responses=True)
    await app.state.redis.ping()

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
        "redis": request.app.state.redis,   # from your FastAPI lifespan
    }

schema = strawberry.Schema(query=Query, context_getter=get_context)
graphql_app = GraphQLRouter(schema)

app = FastAPI(lifespan=lifespan)
app.include_router(graphql_app, prefix="/graphql")
