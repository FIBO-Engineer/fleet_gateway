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

class RobotConnectionStatus(Enum):
    """Robot Connection status"""
    OFFLINE = 0
    ONLINE = 1

class RobotActionStatus(Enum):
    """Robot operational status"""
    IDLE = 0 # Initial state
    OPERATING = 1  # Robot is working
    ERROR = 2  # Robot encountered an error
    CANCELED = 3 # Robot operation was canceled
    SUCCEEDED = 4

class JobOperation(Enum):
    """Warehouse operation types for jobs"""
    TRAVEL = 0
    PICKUP = 1
    DELIVERY = 2

class OrderStatus(Enum):
    """Status of warehouse requests (pickup + delivery pairs)"""
    QUEUING = 0
    IN_PROGRESS = 1
    FAILED = 2
    CANCELED = 3
    COMPLETED = 4
