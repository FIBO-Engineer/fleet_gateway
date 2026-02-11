import os
from supabase import create_client, Client
from typing import overload

from backup.node import Node, NodeType

class GraphOracle:
    def __init__(self, supabase_url, supabase_key):
        self.url: str = supabase_url # os.environ.get("SUPABASE_URL")
        self.key: str = supabase_key # os.environ.get("SUPABASE_KEY")
        self.supabase: Client = create_client(self.url, self.key)

    def getNodesByIds(self, graph_id: int, node_ids: list[int]) -> list[Node]:
        detailed_data = self.supabase.rpc("wh_get_nodes_by_ids", 
                              {"p_graph_id": graph_id, "p_node_ids": node_ids}
                              ).execute()
        nodes: list[Node] = []
        for row in detailed_data.data:
            n = Node(row["id"], row["alias"], row["x"], row["y"], row["height"], row["type"])
            nodes.append(n)
        return nodes

    # Query by Alias
    def getShortestPathByAlias(self, graph_id: int, start_alias: str, end_alias: str) -> list[Node]:
        return (
            self.supabase.rpc("wh_astar_shortest_path",
                            {"p_graph_id": graph_id,  "p_start_alias": start_alias, "p_end_alias": end_alias})
                            .execute().data
        )
    
    # Query by ID
    def getShortestPathById(self, graph_id: int, start_id: int, end_id: int) -> list[int]:
        return (
            self.supabase.rpc("wh_astar_shortest_path", 
                            { "p_graph_id": graph_id, "p_start_vid": start_id, "p_end_vid": end_id})
                            .execute().data
        )

def main():
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    go = GraphOracle(url, key)
    path = go.getShortestPathByAlias(2, start_alias="W3", end_alias="W8")
    nodes = go.getNodesByIds(2, path)
    print(nodes)

if __name__ == "__main__":
    main()