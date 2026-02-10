import networkx as nx
from typing import Sequence, Dict, Any


class PathNetwork(nx.DiGraph):
    def __init__(self, poses: Sequence[Any]) -> None:
        """Create a directed cycle; node i gets pose poses[i]."""
        super().__init__()
        for i, pose in enumerate(poses):
            self.add_node(i, pose=pose)
        n = len(poses)
        for i in range(n):
            self.add_edge(i, (i + 1) % n)

    def place_robot(self, node: int, name: str) -> None:
        """Place a robot at a specific node."""
        if node not in self:
            raise KeyError(f"Node {node} doesn't exist")
        self.nodes[node]['robot'] = name

    def step_robots(self) -> Dict[str, Any]:
        """Advance each robot one step along the directed cycle."""
        positions = [
            (node, data['robot'])
            for node, data in self.nodes(data=True)
            if 'robot' in data
        ]
        for node, _ in positions:
            self.nodes[node].pop('robot', None)

        for node, name in positions:
            succs = list(self.successors(node))
            if succs:
                self.nodes[succs[0]]['robot'] = name

        return self.current_robot_poses()

    def current_robot_poses(self) -> Dict[str, Any]:
        """Return mapping robot_name → current pose."""
        poses: Dict[str, Any] = {}
        for data in self.nodes.values():
            name = data.get('robot')
            if name is not None:
                poses[name] = data['pose']
        return poses
