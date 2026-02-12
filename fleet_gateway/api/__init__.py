"""
GraphQL API layer for Fleet Gateway.

This package contains:
- types.py: GraphQL type definitions
- deserializers.py: Redis data to Python object conversion
- queries.py: Query resolvers
- mutations.py: Mutation resolvers
- subscriptions.py: Subscription resolvers
- schema.py: Combined Strawberry schema
"""

from .schema import schema

__all__ = ["schema"]
