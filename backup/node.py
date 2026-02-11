from dataclasses import dataclass
from enum import Enum

class NodeType(Enum):
    WAYPOINT = 0
    CONVEYOR = 1
    SHELF = 2
    CELL = 3
    DEPOT = 4

@dataclass
class Node:
    node_id: int
    alias: str
    x: float
    y: float
    height: float | None
    node_type: NodeType