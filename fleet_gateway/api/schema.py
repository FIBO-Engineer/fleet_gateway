"""
Combined GraphQL schema for Fleet Gateway.

This module combines all GraphQL components (queries, mutations, subscriptions)
into a single Strawberry schema for use with FastAPI.
"""

import strawberry

from .queries import Query
from .mutations import Mutation
from .subscriptions import Subscription


# Create the combined GraphQL schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription
)
