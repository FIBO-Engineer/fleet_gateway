from dataclasses import dataclass
from enum import Enum

from node import Node

class WarehouseOperation(Enum):
    PICKUP = 0
    DELIVERY = 1

@dataclass
class Task:
    operation: WarehouseOperation
    nodes: list[Node]