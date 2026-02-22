from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import strawberry

from fleet_gateway.enums import NodeType, JobOperation, OrderStatus #, RobotActionStatus, RobotConnectionStatus,
from fleet_gateway.api.types import RobotCell, Job, Node
from fleet_gateway.api.type_resolvers import get_holding_by_robot_cell
from fleet_gateway.order_store import OrderStore


@pytest.fixture
def mock_order_store():
    return AsyncMock(spec=OrderStore)


@pytest.fixture
def mock_info(mock_order_store):
    info = MagicMock(spec=strawberry.types.Info)
    info.context = {"order_store": mock_order_store}
    return info


@pytest.fixture
def sample_node():
    return Node(
        id=1,
        alias="test_node",
        tag_id="tag1",
        x=0.0,
        y=0.0,
        height=0.0,
        node_type=NodeType.WAYPOINT,
    )


@pytest.fixture
def sample_job(sample_node):
    return Job(
        uuid=UUID("12345678-1234-5678-1234-567812345678"),
        status=OrderStatus.QUEUING,
        operation=JobOperation.PICKUP,
        target_node=sample_node,
        request_uuid=None,              # private field (init)
        handling_robot_name="robot1",   # private field (init)
        # DO NOT pass: request=..., handling_robot=... (resolver fields)
    )


@pytest.mark.asyncio
async def test_robot_cell_holding_uuid(sample_job):
    # DO NOT pass holding=... (resolver field)
    robot_cell = RobotCell(height=1.0, holding_uuid=sample_job.uuid)
    assert robot_cell.holding_uuid == sample_job.uuid


@pytest.mark.asyncio
async def test_get_holding_by_robot_cell_with_job(mock_order_store, mock_info, sample_job):
    robot_cell = RobotCell(height=1.0, holding_uuid=sample_job.uuid)

    mock_order_store.get_job.return_value = sample_job

    resolved_job = await get_holding_by_robot_cell(robot_cell, mock_info)

    mock_order_store.get_job.assert_called_once_with(sample_job.uuid)
    assert resolved_job == sample_job


@pytest.mark.asyncio
async def test_get_holding_by_robot_cell_no_holding(mock_order_store, mock_info):
    robot_cell = RobotCell(height=1.0, holding_uuid=None)

    resolved_job = await get_holding_by_robot_cell(robot_cell, mock_info)

    mock_order_store.get_job.assert_not_called()
    assert resolved_job is None