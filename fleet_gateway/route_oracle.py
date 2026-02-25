from __future__ import annotations
from typing import TYPE_CHECKING
import logging

from supabase import create_client, Client

from fleet_gateway.enums import NodeType

_NODE_TYPE_LOOKUP: dict[str, NodeType] = {
    'waypoint': NodeType.WAYPOINT,
    'conveyor': NodeType.CONVEYOR,
    'shelf':    NodeType.SHELF,
    'cell':     NodeType.CELL,
    'depot':    NodeType.DEPOT,
}

if TYPE_CHECKING:
    from fleet_gateway.api.types import Node

logger = logging.getLogger(__name__)


class RouteOracle:
    def __init__(self, supabase_url: str, supabase_key: str, graph_id: int | None):
        self.url: str = supabase_url
        self.key: str = supabase_key
        self.graph_id: int | None = graph_id
        self.supabase: Client = create_client(self.url, self.key)

    def _resolve_graph_id(self, graph_id: int | None) -> int:
        if graph_id is not None:
            return graph_id
        if self.graph_id is not None:
            return self.graph_id
        raise RuntimeError("Unknown graph_id, define in function or ctor")

    def _row_to_node(self, data: dict) -> Node:
        from fleet_gateway.api.types import Node
        node_type = _NODE_TYPE_LOOKUP.get(data["type"])
        if node_type is None:
            logger.warning("Unknown node type %r, falling back to WAYPOINT", data["type"])
            node_type = NodeType.WAYPOINT
        return Node(
            id=data["id"],
            alias=data.get("alias"),
            tag_id=data.get("tag_id"),
            x=data["x"],
            y=data["y"],
            height=data["height"],
            node_type=node_type,
        )

    def get_node_by_tag_id(self, tag_id: str, graph_id: int | None = None) -> Node | None:
        graph_id = self._resolve_graph_id(graph_id)
        res = self.supabase.rpc(
            "wh_get_node_by_tag_id",
            {"p_graph_id": graph_id, "p_tag_id": tag_id},
        ).execute()
        if not res.data:
            return None
        return self._row_to_node(res.data[0])

    def get_node_by_id(self, node_id: int, graph_id: int | None = None) -> Node | None:
        nodes = self.get_nodes_by_ids([node_id], graph_id)
        return nodes[0] if nodes else None

    def get_nodes_by_ids(self, node_ids: list[int], graph_id: int | None = None) -> list[Node]:
        graph_id = self._resolve_graph_id(graph_id)
        res = self.supabase.rpc(
            "wh_get_nodes_by_ids",
            {"p_graph_id": graph_id, "p_node_ids": node_ids},
        ).execute()
        return [self._row_to_node(row) for row in res.data]

    def get_shortest_path_by_alias(self, start_alias: str, end_alias: str, graph_id: int | None = None) -> list[int]:
        graph_id = self._resolve_graph_id(graph_id)
        return (
            self.supabase.rpc(
                "wh_astar_shortest_path",
                {"p_graph_id": graph_id, "p_start_alias": start_alias, "p_end_alias": end_alias},
            ).execute().data
        )

    def get_shortest_path_by_id(self, start_id: int, end_id: int, graph_id: int | None = None) -> list[int]:
        graph_id = self._resolve_graph_id(graph_id)
        return (
            self.supabase.rpc(
                "wh_astar_shortest_path",
                {"p_graph_id": graph_id, "p_start_vid": start_id, "p_end_vid": end_id},
            ).execute().data
        )
