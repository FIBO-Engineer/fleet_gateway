"""
Tests for OrderStore serialization round-trips.

Verifies that Job and Request objects survive serialize → store → deserialize
with all fields intact.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

from fleet_gateway.enums import OrderStatus, JobOperation, NodeType
from fleet_gateway.api.types import Job, Node, Request
from fleet_gateway.helpers.serializers import job_to_dict, node_to_dict, request_to_dict
from fleet_gateway.helpers.deserializers import dict_to_job, dict_to_node, dict_to_request
from fleet_gateway.order_store import OrderStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_node(alias=None, tag_id=None):
    return Node(
        id=42,
        alias=alias,
        tag_id=tag_id,
        x=1.5,
        y=2.5,
        height=0.3,
        node_type=NodeType.SHELF,
    )


def make_job(operation=JobOperation.PICKUP, status=OrderStatus.QUEUING,
             request_uuid=None, alias="shelf1", tag_id="tag42"):
    return Job(
        uuid=uuid4(),
        status=status,
        operation=operation,
        target_node=make_node(alias=alias, tag_id=tag_id),
        request_uuid=request_uuid,
        handling_robot_name="robot1",
    )


def make_request(pickup_uuid=None, delivery_uuid=None):
    return Request(
        uuid=uuid4(),
        pickup_uuid=pickup_uuid or uuid4(),
        delivery_uuid=delivery_uuid or uuid4(),
        handling_robot_name="robot1",
    )


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock()
    r.pipeline = MagicMock()
    return r


# ---------------------------------------------------------------------------
# node_to_dict / dict_to_node round-trip
# ---------------------------------------------------------------------------

class TestNodeSerialization:
    def test_round_trip_with_alias_and_tag(self):
        node = make_node(alias="shelf1", tag_id="tag42")
        d = node_to_dict(node)
        recovered = dict_to_node({k: str(v) if v is not None else str(v) for k, v in d.items()})
        # dict_to_node expects string values (as from Redis)
        raw = {
            'id': str(node.id),
            'alias': str(node.alias),
            'tag_id': str(node.tag_id),
            'x': str(node.x),
            'y': str(node.y),
            'height': str(node.height),
            'node_type': str(node.node_type.value),
        }
        recovered = dict_to_node(raw)
        assert recovered.id == node.id
        assert recovered.alias == node.alias
        assert recovered.tag_id == node.tag_id
        assert recovered.x == node.x
        assert recovered.y == node.y
        assert recovered.height == node.height
        assert recovered.node_type == node.node_type

    def test_round_trip_with_none_alias_and_tag(self):
        """Nodes can have None alias and tag_id (e.g. intermediate waypoints)."""
        node = make_node(alias=None, tag_id=None)
        raw = {
            'id': str(node.id),
            'alias': str(node.alias),   # "None" string
            'tag_id': str(node.tag_id),  # "None" string
            'x': str(node.x),
            'y': str(node.y),
            'height': str(node.height),
            'node_type': str(node.node_type.value),
        }
        # dict_to_node does data['alias'] directly — when serialized via json.dumps/loads,
        # None becomes JSON null which becomes Python None, which is fine.
        # But via str(None) = "None" → dict_to_node would set alias="None" (string)
        # This is a potential issue in direct Redis storage without JSON wrapping.
        # node_to_dict stores None as-is (Python None), then hset converts to empty string.
        # Here we test the JSON round-trip used in job_to_dict → target_node field.
        serialized = json.dumps(node_to_dict(node))
        deserialized_dict = json.loads(serialized)
        recovered = dict_to_node(deserialized_dict)
        assert recovered.alias is None
        assert recovered.tag_id is None


# ---------------------------------------------------------------------------
# job_to_dict / dict_to_job round-trip
# ---------------------------------------------------------------------------

class TestJobSerialization:
    def test_round_trip_basic_job(self):
        job = make_job(operation=JobOperation.PICKUP, status=OrderStatus.QUEUING)
        d = job_to_dict(job)
        recovered = dict_to_job(job.uuid, {k: str(v) for k, v in d.items()})
        assert recovered.uuid == job.uuid
        assert recovered.status == job.status
        assert recovered.operation == job.operation
        assert recovered.handling_robot_name == job.handling_robot_name
        assert recovered.request_uuid == job.request_uuid

    def test_round_trip_with_request_uuid(self):
        req_uuid = uuid4()
        job = make_job(request_uuid=req_uuid)
        d = job_to_dict(job)
        recovered = dict_to_job(job.uuid, {k: str(v) for k, v in d.items()})
        assert recovered.request_uuid == req_uuid

    def test_round_trip_without_request_uuid(self):
        job = make_job(request_uuid=None)
        d = job_to_dict(job)
        # Simulate Redis returning empty string for missing request uuid
        raw = {k: str(v) for k, v in d.items()}
        raw['request'] = ''  # Redis stores "" for None
        recovered = dict_to_job(job.uuid, raw)
        assert recovered.request_uuid is None

    def test_all_statuses_survive_round_trip(self):
        for status in OrderStatus:
            job = make_job(status=status)
            d = job_to_dict(job)
            raw = {k: str(v) for k, v in d.items()}
            recovered = dict_to_job(job.uuid, raw)
            assert recovered.status == status

    def test_all_operations_survive_round_trip(self):
        for op in JobOperation:
            job = make_job(operation=op)
            d = job_to_dict(job)
            raw = {k: str(v) for k, v in d.items()}
            recovered = dict_to_job(job.uuid, raw)
            assert recovered.operation == op

    def test_dict_to_job_returns_none_on_empty_dict(self):
        result = dict_to_job(uuid4(), {})
        assert result is None

    def test_target_node_survives_round_trip(self):
        node = make_node(alias="shelf-A", tag_id="QR99")
        job = make_job(alias="shelf-A", tag_id="QR99")
        d = job_to_dict(job)
        raw = {k: str(v) for k, v in d.items()}
        recovered = dict_to_job(job.uuid, raw)
        assert recovered.target_node.alias == "shelf-A"
        assert recovered.target_node.tag_id == "QR99"
        assert recovered.target_node.id == 42


# ---------------------------------------------------------------------------
# request_to_dict / dict_to_request round-trip
# ---------------------------------------------------------------------------

class TestRequestSerialization:
    def test_round_trip(self):
        req = make_request()
        d = request_to_dict(req)
        recovered = dict_to_request(req.uuid, d)
        assert recovered.uuid == req.uuid
        assert recovered.pickup_uuid == req.pickup_uuid
        assert recovered.delivery_uuid == req.delivery_uuid
        assert recovered.handling_robot_name == req.handling_robot_name

    def test_dict_to_request_returns_none_on_empty_dict(self):
        result = dict_to_request(uuid4(), {})
        assert result is None


# ---------------------------------------------------------------------------
# OrderStore.set_job / get_job via mock Redis
# ---------------------------------------------------------------------------

class TestOrderStoreJobPersistence:
    @pytest.mark.asyncio
    async def test_set_job_returns_true(self, mock_redis):
        store = OrderStore(mock_redis)
        job = make_job()
        result = await store.set_job(job)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_job_calls_hset_with_correct_key(self, mock_redis):
        store = OrderStore(mock_redis)
        job = make_job()
        await store.set_job(job)
        mock_redis.hset.assert_called_once()
        key = mock_redis.hset.call_args[0][0]
        assert key == f"job:{str(job.uuid)}"

    @pytest.mark.asyncio
    async def test_get_job_returns_none_when_not_found(self, mock_redis):
        mock_redis.hgetall.return_value = {}
        store = OrderStore(mock_redis)
        result = await store.get_job(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_job_round_trip(self, mock_redis):
        """Simulate set_job writing data, then get_job reading it back."""
        job = make_job(operation=JobOperation.DELIVERY, status=OrderStatus.IN_PROGRESS)
        stored_data: dict = {}

        async def fake_hset(key, mapping):
            stored_data.update({k: str(v) for k, v in mapping.items()})

        async def fake_hgetall(key):
            return stored_data

        mock_redis.hset = fake_hset
        mock_redis.hgetall = fake_hgetall

        store = OrderStore(mock_redis)
        await store.set_job(job)
        recovered = await store.get_job(job.uuid)

        assert recovered is not None
        assert recovered.uuid == job.uuid
        assert recovered.status == job.status
        assert recovered.operation == job.operation
        assert recovered.handling_robot_name == job.handling_robot_name


# ---------------------------------------------------------------------------
# OrderStore.get_request_status derived logic
# ---------------------------------------------------------------------------

class TestGetRequestStatus:
    @pytest.mark.asyncio
    async def test_both_completed_returns_completed(self, mock_redis):
        pickup = make_job(status=OrderStatus.COMPLETED)
        delivery = make_job(status=OrderStatus.COMPLETED)
        req = make_request(pickup_uuid=pickup.uuid, delivery_uuid=delivery.uuid)

        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(side_effect=[pickup, delivery])

        status = await store.get_request_status(req)
        assert status == OrderStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_pickup_failed_returns_failed(self, mock_redis):
        pickup = make_job(status=OrderStatus.FAILED)
        delivery = make_job(status=OrderStatus.QUEUING)
        req = make_request(pickup_uuid=pickup.uuid, delivery_uuid=delivery.uuid)

        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(side_effect=[pickup, delivery])

        status = await store.get_request_status(req)
        assert status == OrderStatus.FAILED

    @pytest.mark.asyncio
    async def test_delivery_failed_returns_failed(self, mock_redis):
        pickup = make_job(status=OrderStatus.COMPLETED)
        delivery = make_job(status=OrderStatus.FAILED)
        req = make_request(pickup_uuid=pickup.uuid, delivery_uuid=delivery.uuid)

        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(side_effect=[pickup, delivery])

        status = await store.get_request_status(req)
        assert status == OrderStatus.FAILED

    @pytest.mark.asyncio
    async def test_either_canceled_returns_canceled(self, mock_redis):
        pickup = make_job(status=OrderStatus.CANCELED)
        delivery = make_job(status=OrderStatus.QUEUING)
        req = make_request(pickup_uuid=pickup.uuid, delivery_uuid=delivery.uuid)

        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(side_effect=[pickup, delivery])

        status = await store.get_request_status(req)
        assert status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_either_in_progress_returns_in_progress(self, mock_redis):
        pickup = make_job(status=OrderStatus.IN_PROGRESS)
        delivery = make_job(status=OrderStatus.QUEUING)
        req = make_request(pickup_uuid=pickup.uuid, delivery_uuid=delivery.uuid)

        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(side_effect=[pickup, delivery])

        status = await store.get_request_status(req)
        assert status == OrderStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_both_queuing_returns_queuing(self, mock_redis):
        pickup = make_job(status=OrderStatus.QUEUING)
        delivery = make_job(status=OrderStatus.QUEUING)
        req = make_request(pickup_uuid=pickup.uuid, delivery_uuid=delivery.uuid)

        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(side_effect=[pickup, delivery])

        status = await store.get_request_status(req)
        assert status == OrderStatus.QUEUING

    @pytest.mark.asyncio
    async def test_failed_takes_priority_over_canceled(self, mock_redis):
        """FAILED should take priority over CANCELED per the status hierarchy."""
        pickup = make_job(status=OrderStatus.FAILED)
        delivery = make_job(status=OrderStatus.CANCELED)
        req = make_request(pickup_uuid=pickup.uuid, delivery_uuid=delivery.uuid)

        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(side_effect=[pickup, delivery])

        status = await store.get_request_status(req)
        assert status == OrderStatus.FAILED

    @pytest.mark.asyncio
    async def test_raises_when_jobs_not_found(self, mock_redis):
        req = make_request()
        store = OrderStore(mock_redis)
        store.get_job = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError):
            await store.get_request_status(req)
