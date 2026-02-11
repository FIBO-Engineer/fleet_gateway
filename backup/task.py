from dataclasses import dataclass
from enum import Enum

from node import Node

class WarehouseOperation(Enum):
    TRAVEL = 0
    PICKUP = 1
    DELIVERY = 2

@dataclass
class Task:
    operation: WarehouseOperation
    nodes: list[Node]