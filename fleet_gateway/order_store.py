"""
Order Store - Centralized Job & Request management and persistence.

Handles all request CRUD operations, persistence to Redis, and request lifecycle management.
"""

import redis.asyncio as redis
from uuid import UUID
from typing import TYPE_CHECKING

# from fleet_gateway.api.types import Request
# from fleet_gateway.helpers.serializers import request_to_dict
# from fleet_gateway.enums import RequestStatus


class OrderStore():
    def __init__(self, redis_client: redis.Redis):
        """Initialize JobStore with Redis client"""
        self.redis = redis_client