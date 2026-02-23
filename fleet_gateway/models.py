"""
Plain Python dataclasses for internal robot state.

These mirror the strawberry types in api/types.py but have no GraphQL
dependency, allowing robot.py to import them without creating a circular
import through the api layer:

    types.py -> type_resolvers.py -> fleet_handler.py -> robot.py -> types.py

robot.py imports from this module at runtime; api/types.py defines the
equivalent strawberry types for GraphQL exposure. Duck typing bridges them
at GraphQL resolution time.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Pose:
    timestamp: datetime
    x: float
    y: float
    a: float


@dataclass
class Tag:
    timestamp: datetime
    qr_id: str


@dataclass
class MobileBaseState:
    tag: Tag | None
    pose: Pose | None


@dataclass
class PiggybackState:
    timestamp: datetime
    lift: float
    turntable: float
    slide: float
    hook_left: float
    hook_right: float


@dataclass
class RobotCell:
    height: float
    holding_uuid: UUID | None = None
