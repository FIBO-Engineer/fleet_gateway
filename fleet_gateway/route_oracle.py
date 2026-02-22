import os
from supabase import create_client, Client

from fleet_gateway.api.types import Node
from fleet_gateway.enums import NodeType


class RouteOracle:
    def __init__(self, supabase_url: str, supabase_key: str, graph_id: int | None):
        self.url: str = supabase_url # os.environ.get("SUPABASE_URL")
        self.key: str = supabase_key # os.environ.get("SUPABASE_KEY")
        self.graph_id: int | None = graph_id
        self.supabase: Client = create_client(self.url, self.key)

    def getNodeByTagId(self, graph_id: int | None, tag_id: int) -> Node | None:
        if graph_id is None:
            if self.graph_id is None:
                raise RuntimeError("Unknown graph_id, define in function or ctor")
            else:
                graph_id = self.graph_id
        res = self.supabase.rpc("wh_get_node_by_tag_id",
                                      {"p_graph_id": graph_id, "p_tag_id": tag_id}
                                      ).execute()
        if not res.data:
            return None
        data = res.data[0]
        return Node(data["id"], data.get("alias"), data["tag_id"], data["x"], data["y"], data.get("height"), NodeType(data["type"]))

    def getNodeById(self, graph_id: int | None, node_id: int) -> Node | None:
        return node[0] if (node := self.getNodesByIds(graph_id, [node_id])) is not [] else None

    def getNodesByIds(self, graph_id: int | None, node_ids: list[int]) -> list[Node]:
        if graph_id is None:
            if self.graph_id is None:
                raise RuntimeError("Unknown graph_id, define in function or ctor")
            else:
                graph_id = self.graph_id
        detailed_data = self.supabase.rpc("wh_get_nodes_by_ids",
                              {"p_graph_id": graph_id, "p_node_ids": node_ids}
                              ).execute()
        nodes: list[Node] = []
        for row in detailed_data.data:
            n = Node(
                id=row["id"],
                alias=row.get("alias"),
                x=row["x"],
                y=row["y"],
                height=row.get("height"),
                node_type=NodeType(row["type"])
            )
            nodes.append(n)
        return nodes

    # Query by Alias
    def getShortestPathByAlias(self, graph_id: int | None, start_alias: str, end_alias: str) -> list[Node]:
        if graph_id is None:
            if self.graph_id is None:
                raise RuntimeError("Unknown graph_id, define in function or ctor")
            else:
                graph_id = self.graph_id
        return (
            self.supabase.rpc("wh_astar_shortest_path",
                            {"p_graph_id": graph_id,  "p_start_alias": start_alias, "p_end_alias": end_alias})
                            .execute().data
        )
    
    # Query by ID
    def getShortestPathById(self, graph_id: int | None, start_id: int, end_id: int) -> list[int]:
        if graph_id is None:
            if self.graph_id is None:
                raise RuntimeError("Unknown graph_id, define in function or ctor")
            else:
                graph_id = self.graph_id
        return (
            self.supabase.rpc("wh_astar_shortest_path", 
                            { "p_graph_id": graph_id, "p_start_vid": start_id, "p_end_vid": end_id})
                            .execute().data
        )

def main():
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    ro = RouteOracle(url, key)
    path = ro.getShortestPathByAlias(2, start_alias="W3", end_alias="W8")
    nodes = ro.getNodesByIds(2, path)
    print(nodes)

if __name__ == "__main__":
    main()