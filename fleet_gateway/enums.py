"""
Shared enum definitions for the fleet gateway system.

These are plain Python enums that match the ROS message definitions.
The schema.py file wraps these with @strawberry.enum for GraphQL.
"""

from enum import Enum


class NodeType(Enum):
    """Node types in the warehouse path network"""
    WAYPOINT = 0
    CONVEYOR = 1
    SHELF = 2
    CELL = 3
    DEPOT = 4


class RobotStatus(Enum):
    """Robot operational status"""
    OFFLINE = 0
    IDLE = 1
    INACTIVE = 2  # User manually disabled this robot
    BUSY = 3
    ERROR = 4  # Robot encountered an error


class WarehouseOperation(Enum):
    """Warehouse operation types for jobs"""
    TRAVEL = 0
    PICKUP = 1
    DELIVERY = 2


class RequestStatus(Enum):
    """Status of warehouse requests (pickup + delivery pairs)"""
    CANCELLED = 0
    FAILED = 1
    IN_PROGRESS = 2
    COMPLETED = 3
