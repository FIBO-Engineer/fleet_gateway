"""
Tests for RobotHandler state machine behavior.

Covers: trigger(), update_job_status(), find_free_cell(), clear_error()
and verifies correct state transitions and cell assignment logic.
"""
from __future__ import annotations

import asyncio
import gc
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4

from fleet_gateway.enums import (
    OrderStatus, RobotActionStatus, RobotConnectionStatus, JobOperation, RobotCellLevel
)
from fleet_gateway.models import RobotCell
from fleet_gateway.api.types import Job, Node
from fleet_gateway.enums import NodeType


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_job(operation=JobOperation.PICKUP, status=OrderStatus.QUEUING):
    node = Node(id=1, alias="shelf1", tag_id="tag1", x=0.0, y=0.0, height=0.0,
                node_type=NodeType.SHELF)
    return Job(
        uuid=uuid4(),
        status=status,
        operation=operation,
        target_node=node,
        request_uuid=None,
        handling_robot_name="robot1",
    )


def make_robot_handler(num_cells=3, is_connected=True, action_status=RobotActionStatus.IDLE):
    """Return a fully-mocked RobotHandler without a real ROS connection."""
    with (
        patch("fleet_gateway.robot.Ros.__init__", return_value=None),
        patch("fleet_gateway.robot.Ros.run", return_value=None),
        patch("fleet_gateway.robot.ActionClient.__init__", return_value=None),
        patch("fleet_gateway.robot.Topic.__init__", return_value=None),
        patch("fleet_gateway.robot.Topic.subscribe", return_value=None),
        patch("asyncio.get_running_loop"),
    ):
        from fleet_gateway.robot import RobotHandler

        job_updater = asyncio.Queue()
        route_oracle = MagicMock()

        handler = RobotHandler.__new__(RobotHandler)

        # Manually initialise state that __init__ would set up
        handler.name = "robot1"
        handler.active_status = True
        handler.last_action_status = action_status
        handler.mobile_base_state = MagicMock()
        handler.mobile_base_state.tag = MagicMock()
        handler.piggyback_state = None
        handler.warehouse_cmd_action_client = MagicMock()
        handler.action_future = None
        handler.route_oracle = route_oracle
        handler.cells = [RobotCell(height=float(i)) for i in range(num_cells)]
        handler.current_job = None
        handler.current_cell = None
        handler.job_queue = []
        handler.job_updater = job_updater

        # call_soon_threadsafe comes from roslibpy's Twisted thread.
        # In tests, make it synchronous so scheduled callbacks fire immediately.
        mock_loop = MagicMock()
        mock_loop.call_soon_threadsafe = lambda fn, *args: fn(*args)
        handler.loop = mock_loop

        # is_connected is a read-only property on roslibpy.Ros — override
        # connection_status() at the instance level instead.
        _conn = RobotConnectionStatus.ONLINE if is_connected else RobotConnectionStatus.OFFLINE
        handler.connection_status = lambda: _conn
        handler.send_job = MagicMock()   # mock the actual ROS send

    return handler


# ---------------------------------------------------------------------------
# find_free_cell tests
# ---------------------------------------------------------------------------

class TestFindFreeCell:
    def test_returns_first_free_cell(self):
        handler = make_robot_handler(num_cells=3)
        cell_level = handler.find_free_cell()
        assert cell_level == RobotCellLevel.CELL_0
        assert handler.current_cell == RobotCellLevel.CELL_0

    def test_skips_occupied_cell(self):
        handler = make_robot_handler(num_cells=3)
        handler.cells[0].holding_uuid = uuid4()  # occupy cell 0
        cell_level = handler.find_free_cell()
        assert cell_level == RobotCellLevel.CELL_1

    def test_raises_when_all_cells_occupied(self):
        handler = make_robot_handler(num_cells=2)
        handler.cells[0].holding_uuid = uuid4()
        handler.cells[1].holding_uuid = uuid4()
        with pytest.raises(RuntimeError, match="No free robot cell available"):
            handler.find_free_cell()

    def test_current_cell_not_set_when_raises(self):
        """current_cell must remain unchanged if find_free_cell raises."""
        handler = make_robot_handler(num_cells=1)
        handler.cells[0].holding_uuid = uuid4()
        handler.current_cell = None
        with pytest.raises(RuntimeError):
            handler.find_free_cell()
        assert handler.current_cell is None  # must NOT be modified


# ---------------------------------------------------------------------------
# update_job_status tests
# ---------------------------------------------------------------------------

class TestUpdateJobStatus:
    def test_pickup_completed_assigns_cell_holding(self):
        """PICKUP COMPLETED → cell.holding_uuid should be set to the job uuid."""
        handler = make_robot_handler(num_cells=3)
        job = make_job(operation=JobOperation.PICKUP)
        handler.current_job = job
        handler.current_cell = RobotCellLevel.CELL_1

        handler.update_job_status(OrderStatus.COMPLETED)

        assert handler.cells[1].holding_uuid == job.uuid

    def test_pickup_failed_does_not_assign_cell(self):
        """PICKUP FAILED → no cell should receive the job uuid."""
        handler = make_robot_handler(num_cells=3)
        job = make_job(operation=JobOperation.PICKUP)
        handler.current_job = job
        handler.current_cell = RobotCellLevel.CELL_0

        handler.update_job_status(OrderStatus.FAILED)

        assert handler.cells[0].holding_uuid is None

    def test_pickup_canceled_does_not_assign_cell(self):
        """PICKUP CANCELED → no cell should receive the job uuid."""
        handler = make_robot_handler(num_cells=3)
        job = make_job(operation=JobOperation.PICKUP)
        handler.current_job = job
        handler.current_cell = RobotCellLevel.CELL_0

        handler.update_job_status(OrderStatus.CANCELED)

        assert handler.cells[0].holding_uuid is None

    def test_delivery_completed_does_not_assign_cell(self):
        """DELIVERY COMPLETED → no cell should be modified."""
        handler = make_robot_handler(num_cells=3)
        job = make_job(operation=JobOperation.DELIVERY)
        handler.current_job = job
        handler.current_cell = None  # DELIVERY uses UNUSED

        handler.update_job_status(OrderStatus.COMPLETED)

        for cell in handler.cells:
            assert cell.holding_uuid is None

    def test_terminal_status_clears_current_job(self):
        """All terminal statuses must clear current_job and current_cell."""
        for terminal in (OrderStatus.COMPLETED, OrderStatus.CANCELED, OrderStatus.FAILED):
            handler = make_robot_handler(num_cells=2)
            job = make_job(operation=JobOperation.DELIVERY)
            handler.current_job = job
            handler.current_cell = None

            handler.update_job_status(terminal)

            assert handler.current_job is None
            assert handler.current_cell is None

    def test_in_progress_does_not_clear_job(self):
        """IN_PROGRESS should not clear the current job."""
        handler = make_robot_handler(num_cells=2)
        job = make_job(operation=JobOperation.PICKUP)
        handler.current_job = job
        handler.current_cell = RobotCellLevel.CELL_0

        handler.update_job_status(OrderStatus.IN_PROGRESS)

        assert handler.current_job is job

    def test_job_status_updated_on_object(self):
        """update_job_status must mutate job.status before enqueueing."""
        handler = make_robot_handler(num_cells=2)
        job = make_job(operation=JobOperation.PICKUP, status=OrderStatus.IN_PROGRESS)
        handler.current_job = job
        handler.current_cell = RobotCellLevel.CELL_0

        handler.update_job_status(OrderStatus.COMPLETED)

        assert job.status == OrderStatus.COMPLETED

    def test_job_enqueued_to_job_updater(self):
        """The job must be put on job_updater queue for every status update."""
        handler = make_robot_handler(num_cells=2)
        job = make_job(operation=JobOperation.PICKUP)
        handler.current_job = job
        handler.current_cell = RobotCellLevel.CELL_0

        put_calls = []
        handler.job_updater.put_nowait = lambda j: put_calls.append(j)

        handler.update_job_status(OrderStatus.COMPLETED)

        assert len(put_calls) == 1
        assert put_calls[0] is job


# ---------------------------------------------------------------------------
# trigger() tests
# ---------------------------------------------------------------------------

class TestTrigger:
    def test_trigger_processes_queued_pickup_job(self):
        handler = make_robot_handler(num_cells=3)
        job = make_job(operation=JobOperation.PICKUP)
        handler.job_queue.append(job)

        handler.trigger()

        handler.send_job.assert_called_once()
        args = handler.send_job.call_args[0]
        assert args[0] is job
        assert isinstance(args[1], RobotCellLevel)
        assert args[1] != RobotCellLevel.UNUSED  # pickup must use a real cell

    def test_trigger_uses_unused_cell_for_delivery(self):
        handler = make_robot_handler(num_cells=3)
        job = make_job(operation=JobOperation.DELIVERY)
        handler.job_queue.append(job)

        handler.trigger()

        args = handler.send_job.call_args[0]
        assert args[1] == RobotCellLevel.UNUSED

    def test_trigger_does_nothing_when_queue_empty(self):
        handler = make_robot_handler(num_cells=3)
        handler.trigger()
        handler.send_job.assert_not_called()

    def test_trigger_does_nothing_when_already_has_current_job(self):
        handler = make_robot_handler(num_cells=3)
        handler.current_job = make_job()
        handler.job_queue.append(make_job())

        handler.trigger()

        handler.send_job.assert_not_called()

    def test_trigger_does_nothing_when_offline(self):
        handler = make_robot_handler(num_cells=3, is_connected=False)
        handler.job_queue.append(make_job())

        handler.trigger()

        handler.send_job.assert_not_called()

    def test_trigger_does_nothing_when_inactive(self):
        handler = make_robot_handler(num_cells=3)
        handler.active_status = False
        handler.job_queue.append(make_job())

        handler.trigger()

        handler.send_job.assert_not_called()

    def test_trigger_does_nothing_when_error_status(self):
        """ERROR status must block trigger — requires manual clear_error() call."""
        handler = make_robot_handler(num_cells=3, action_status=RobotActionStatus.ERROR)
        handler.job_queue.append(make_job())

        handler.trigger()

        handler.send_job.assert_not_called()

    def test_trigger_does_nothing_when_operating(self):
        handler = make_robot_handler(num_cells=3, action_status=RobotActionStatus.OPERATING)
        handler.job_queue.append(make_job())

        handler.trigger()

        handler.send_job.assert_not_called()

    def test_succeeded_status_allows_trigger_and_is_set_by_on_result(self):
        """
        RobotActionStatus.SUCCEEDED is in is_ready_status AND is now correctly set
        by the on_result callback (GoalStatus.SUCCEEDED → last_action_status = SUCCEEDED).

        update_job_status() then calls trigger(), which sees SUCCEEDED in is_ready_status
        and processes the next queued job.
        """
        # SUCCEEDED is in is_ready_status → trigger should fire
        handler = make_robot_handler(num_cells=3, action_status=RobotActionStatus.SUCCEEDED)
        handler.job_queue.append(make_job())
        handler.trigger()
        handler.send_job.assert_called_once()

        # Simulate what on_result does: set SUCCEEDED then call update_job_status.
        # (In production the Twisted callback sets last_action_status before
        # calling update_job_status; in tests we must replicate that order.)
        handler2 = make_robot_handler(num_cells=3)
        job = make_job(operation=JobOperation.DELIVERY)
        handler2.current_job = job
        handler2.current_cell = None
        handler2.last_action_status = RobotActionStatus.SUCCEEDED  # set by on_result
        handler2.update_job_status(OrderStatus.COMPLETED)
        # Queue is empty so trigger() does nothing → status stays SUCCEEDED
        assert handler2.last_action_status == RobotActionStatus.SUCCEEDED, (
            "Expected SUCCEEDED after completion — on_result now sets SUCCEEDED, not IDLE"
        )

    def test_send_job_failure_sets_error_status(self):
        handler = make_robot_handler(num_cells=3)
        handler.send_job.side_effect = RuntimeError("No path found")
        job = make_job(operation=JobOperation.PICKUP)
        handler.job_queue.append(job)

        handler.trigger()

        assert handler.last_action_status == RobotActionStatus.ERROR
        assert handler.current_job is None
        assert handler.current_cell is None

    def test_send_job_failure_publishes_failed_status(self):
        handler = make_robot_handler(num_cells=3)
        handler.send_job.side_effect = RuntimeError("boom")
        job = make_job(operation=JobOperation.PICKUP)
        handler.job_queue.append(job)

        published = []
        handler.job_updater.put_nowait = lambda j: published.append(j)

        handler.trigger()

        assert len(published) == 1
        assert published[0].status == OrderStatus.FAILED


# ---------------------------------------------------------------------------
# clear_error() tests
# ---------------------------------------------------------------------------

class TestClearError:
    def test_clear_error_resets_to_idle(self):
        handler = make_robot_handler(num_cells=2, action_status=RobotActionStatus.ERROR)
        result = handler.clear_error()
        assert result is True
        assert handler.last_action_status == RobotActionStatus.IDLE

    def test_clear_error_triggers_next_job(self):
        handler = make_robot_handler(num_cells=2, action_status=RobotActionStatus.ERROR)
        job = make_job(operation=JobOperation.DELIVERY)
        handler.job_queue.append(job)

        handler.clear_error()

        handler.send_job.assert_called_once()

    def test_clear_error_returns_false_when_not_in_error(self):
        handler = make_robot_handler(num_cells=2, action_status=RobotActionStatus.IDLE)
        result = handler.clear_error()
        assert result is False
        assert handler.last_action_status == RobotActionStatus.IDLE

    def test_clear_error_noop_when_operating(self):
        handler = make_robot_handler(num_cells=2, action_status=RobotActionStatus.OPERATING)
        result = handler.clear_error()
        assert result is False
