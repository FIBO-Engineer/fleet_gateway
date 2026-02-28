"""
Tests for WarehouseController.

Key focus: the asyncio.create_task() GC bug — the background job_updater task
has no stored reference. This test suite verifies whether the task survives
garbage collection and actually processes jobs.
"""
from __future__ import annotations

import asyncio
import gc
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fleet_gateway.enums import OrderStatus, JobOperation, NodeType
from fleet_gateway.api.types import Job, Node


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_job():
    node = Node(id=1, alias="n1", tag_id="t1", x=0.0, y=0.0, height=0.0,
                node_type=NodeType.SHELF)
    return Job(
        uuid=uuid4(),
        status=OrderStatus.IN_PROGRESS,
        operation=JobOperation.PICKUP,
        target_node=node,
        request_uuid=None,
        handling_robot_name="robot1",
    )


@pytest.fixture
def mock_fleet_handler():
    fh = MagicMock()
    fh.get_robot.return_value = MagicMock()
    return fh


@pytest.fixture
def mock_order_store():
    os = AsyncMock()
    os.set_job.return_value = True
    os.set_request.return_value = True
    return os


@pytest.fixture
def mock_route_oracle():
    ro = MagicMock()
    node = Node(id=1, alias="n1", tag_id="t1", x=0.0, y=0.0, height=0.0,
                node_type=NodeType.SHELF)
    ro.get_node.return_value = node
    ro.get_nodes.return_value = [node]
    ro.get_shortest_path.return_value = [1]
    return ro


# ---------------------------------------------------------------------------
# GC bug test
# ---------------------------------------------------------------------------

class TestJobUpdaterTaskGCBug:
    """
    BUG: asyncio.create_task(handle_job_updater(...)) in WarehouseController.__init__
    stores no reference to the created task. Python's event loop holds only weak
    refs to tasks; if the task object has no strong reference elsewhere, it is
    eligible for garbage collection while suspended at `await queue.get()`.

    This test suite verifies:
    1. The task has no strong reference on the WarehouseController instance.
    2. After forced GC the task may be destroyed, causing jobs to go unprocessed.
    """

    @pytest.mark.asyncio
    async def test_task_reference_stored_on_controller(self, mock_fleet_handler, mock_order_store, mock_route_oracle):
        """WarehouseController must store the background task on self._updater_task."""
        from fleet_gateway.warehouse_controller import WarehouseController

        queue = asyncio.Queue()
        wc = WarehouseController(queue, mock_fleet_handler, mock_order_store, mock_route_oracle)

        await asyncio.sleep(0)

        task_attrs = [v for v in vars(wc).values() if isinstance(v, asyncio.Task)]
        assert len(task_attrs) == 1, (
            "Expected exactly one Task stored on the controller. "
            "Missing reference means the task can be GC'd."
        )
        assert not task_attrs[0].done()

        for task in asyncio.all_tasks():
            if not task.done() and task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    @pytest.mark.asyncio
    async def test_task_survives_and_processes_job(self, mock_fleet_handler, mock_order_store, mock_route_oracle):
        """
        After creating WarehouseController, putting a job on the queue should
        trigger set_job(). This tests the happy path under normal conditions.
        If GC collects the task, set_job will never be called.
        """
        from fleet_gateway.warehouse_controller import WarehouseController

        queue = asyncio.Queue()
        wc = WarehouseController(queue, mock_fleet_handler, mock_order_store, mock_route_oracle)

        # Let the background task start
        await asyncio.sleep(0)

        job = make_job()
        queue.put_nowait(job)

        # Allow the event loop to process the queue item
        await asyncio.sleep(0)
        await asyncio.sleep(0)  # two ticks to be safe

        mock_order_store.set_job.assert_called_once_with(job)

        # Cleanup
        for task in asyncio.all_tasks():
            if not task.done() and task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    @pytest.mark.asyncio
    async def test_task_gone_after_gc(self, mock_fleet_handler, mock_order_store, mock_route_oracle):
        """
        Force GC after controller creation.  If the task holds no strong
        reference, the task will be destroyed during collection and a subsequent
        job put on the queue will NOT be processed.

        NOTE: CPython's reference-counting GC will keep the task alive as long
        as the asyncio Queue waiter chain holds a reference. This test documents
        the risk but may pass even with the bug present on CPython due to
        implementation details.  Under PyPy or with cyclic-only GC the risk is
        higher.
        """
        from fleet_gateway.warehouse_controller import WarehouseController

        queue = asyncio.Queue()
        wc = WarehouseController(queue, mock_fleet_handler, mock_order_store, mock_route_oracle)

        await asyncio.sleep(0)

        # Force full garbage collection
        gc.collect()
        gc.collect()
        gc.collect()

        job = make_job()
        queue.put_nowait(job)

        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # If the task survived GC (CPython typical case), set_job was called
        # If not, the job silently goes nowhere — the bug manifests
        call_count = mock_order_store.set_job.call_count
        assert call_count == 1, (
            f"Expected set_job to be called once (task alive after GC), "
            f"but was called {call_count} time(s). "
            f"0 calls = task was GC'd (bug reproduced)."
        )

        for task in asyncio.all_tasks():
            if not task.done() and task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass


# ---------------------------------------------------------------------------
# Bug: Job() / Request() positional-arg constructor mismatch
# ---------------------------------------------------------------------------

class TestJobConstructorBug:
    """
    BUG: @strawberry.type generates keyword-only __init__ (note the leading `*`).
    WarehouseController calls Job() and Request() with positional arguments,
    which raises TypeError at runtime.

    All mutations (send_job_order, send_request_order) are broken.
    """

    def test_job_init_is_keyword_only(self):
        """Confirm that Job.__init__ rejects positional arguments."""
        import inspect
        from fleet_gateway.api.types import Job
        sig = inspect.signature(Job)
        params = list(sig.parameters.values())
        # A keyword-only parameter has kind == KEYWORD_ONLY
        # (the `*` in the signature makes all params keyword-only)
        kinds = {p.kind for p in params}
        assert inspect.Parameter.KEYWORD_ONLY in kinds, \
            "Job.__init__ has no keyword-only params — unexpected"
        assert inspect.Parameter.POSITIONAL_OR_KEYWORD not in kinds, \
            "Job.__init__ still accepts positional args — check strawberry version"

    def test_positional_job_construction_raises(self):
        """warehouse_controller.py uses positional args → TypeError."""
        from fleet_gateway.api.types import Job, Node
        from uuid import uuid4
        node = Node(id=1, alias=None, tag_id=None, x=0.0, y=0.0, height=0.0,
                    node_type=NodeType.WAYPOINT)
        with pytest.raises(TypeError):
            # This is exactly what warehouse_controller.py:62 does
            Job(uuid4(), OrderStatus.QUEUING, JobOperation.TRAVEL, node, None, "robot1")

    def test_keyword_job_construction_succeeds(self):
        """Keyword arguments must work — this is the correct form."""
        from fleet_gateway.api.types import Job, Node
        from uuid import uuid4
        node = Node(id=1, alias=None, tag_id=None, x=0.0, y=0.0, height=0.0,
                    node_type=NodeType.WAYPOINT)
        job = Job(uuid=uuid4(), status=OrderStatus.QUEUING, operation=JobOperation.TRAVEL,
                  target_node=node, request_uuid=None, handling_robot_name="robot1")
        assert job is not None

    def test_request_init_is_keyword_only(self):
        """Confirm that Request.__init__ also rejects positional arguments."""
        import inspect
        from fleet_gateway.api.types import Request
        sig = inspect.signature(Request)
        params = list(sig.parameters.values())
        kinds = {p.kind for p in params}
        assert inspect.Parameter.KEYWORD_ONLY in kinds

    def test_positional_request_construction_raises(self):
        """warehouse_controller.py:89 uses positional args → TypeError."""
        from fleet_gateway.api.types import Request
        from uuid import uuid4
        with pytest.raises(TypeError):
            Request(uuid4(), uuid4(), uuid4(), "robot1")

    @pytest.mark.asyncio
    async def test_accept_job_order_succeeds_with_keyword_args(
            self, mock_fleet_handler, mock_order_store, mock_route_oracle):
        """accept_job_order must return success now that keyword args are used."""
        from fleet_gateway.warehouse_controller import WarehouseController
        from fleet_gateway.api.types import JobOrderInput

        queue = asyncio.Queue()
        wc = WarehouseController(queue, mock_fleet_handler, mock_order_store, mock_route_oracle)

        job_order = MagicMock(spec=JobOrderInput)
        job_order.robot_name = "robot1"
        job_order.target_node_id = 1
        job_order.operation = JobOperation.TRAVEL

        result = await wc.accept_job_order(job_order)

        assert result.success is True
        mock_order_store.set_job.assert_called_once()
        mock_fleet_handler.assign_job.assert_called_once()

        for task in asyncio.all_tasks():
            if not task.done() and task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    @pytest.mark.asyncio
    async def test_accept_request_order_succeeds_with_keyword_args(
            self, mock_fleet_handler, mock_order_store, mock_route_oracle):
        """accept_request_order must return success now that keyword args are used."""
        from fleet_gateway.warehouse_controller import WarehouseController
        from fleet_gateway.api.types import RequestOrderInput, RequestInput

        queue = asyncio.Queue()
        wc = WarehouseController(queue, mock_fleet_handler, mock_order_store, mock_route_oracle)

        request_order = MagicMock(spec=RequestOrderInput)
        request_order.robot_name = "robot1"
        request_order.request = MagicMock(spec=RequestInput)
        request_order.request.pickup_node_id = 1
        request_order.request.delivery_node_id = 1

        result = await wc.accept_request_order(request_order)

        assert result.success is True
        assert mock_order_store.set_job.call_count == 2
        assert mock_order_store.set_request.call_count == 1
        assert mock_fleet_handler.assign_job.call_count == 2

        for task in asyncio.all_tasks():
            if not task.done() and task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass


# ---------------------------------------------------------------------------
# Result type constructor bug (same positional-arg issue)
# ---------------------------------------------------------------------------

class TestResultTypeConstructorBug:
    """
    BUG: JobOrderResult, RequestOrderResult are also @strawberry.type and also
    have keyword-only __init__. warehouse_controller.py:59 uses positional args
    for JobOrderResult too — so even the error paths are broken.
    """

    def test_job_order_result_init_is_keyword_only(self):
        import inspect
        from fleet_gateway.api.types import JobOrderResult
        sig = inspect.signature(JobOrderResult)
        params = list(sig.parameters.values())
        kinds = {p.kind for p in params}
        assert inspect.Parameter.KEYWORD_ONLY in kinds
        assert inspect.Parameter.POSITIONAL_OR_KEYWORD not in kinds

    def test_positional_job_order_result_raises(self):
        from fleet_gateway.api.types import JobOrderResult
        with pytest.raises(TypeError):
            JobOrderResult(False, "msg", None)

    def test_keyword_job_order_result_succeeds(self):
        from fleet_gateway.api.types import JobOrderResult
        r = JobOrderResult(success=False, message="msg", job=None)
        assert r.success is False

    @pytest.mark.asyncio
    async def test_error_path_returns_failure_gracefully(
            self, mock_fleet_handler, mock_order_store, mock_route_oracle):
        """Validation-failure path must now return a failure result, not raise."""
        from fleet_gateway.warehouse_controller import WarehouseController
        from fleet_gateway.api.types import JobOrderInput

        mock_fleet_handler.get_robot.return_value = None

        queue = asyncio.Queue()
        wc = WarehouseController(queue, mock_fleet_handler, mock_order_store, mock_route_oracle)

        job_order = MagicMock(spec=JobOrderInput)
        job_order.robot_name = "nonexistent"
        job_order.target_node_id = 1
        job_order.operation = JobOperation.TRAVEL

        result = await wc.accept_job_order(job_order)

        assert result.success is False
        assert result.job is None

        for task in asyncio.all_tasks():
            if not task.done() and task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
