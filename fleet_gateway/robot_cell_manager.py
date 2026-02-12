"""Cell allocation and tracking for robot storage."""

from fleet_gateway.robot_handler import RobotHandler


class RobotCellManager:
    """Manages cell allocation and tracking for robot fleet."""

    def __init__(self, robot_handlers: list[RobotHandler]):
        """Initialize cell manager with robot handlers."""
        # Track which cell holds which request for each robot
        # robot_name -> list of request_uuids (None if cell is free)
        self.robot_cell_holdings: dict[str, list[str | None]] = {
            handler.state.name: [None] * len(handler.state.robot_cell_heights)
            for handler in robot_handlers
        }

        # Track cell heights for each robot (for height matching)
        self.robot_cell_heights: dict[str, list[float]] = {
            handler.state.name: handler.state.robot_cell_heights.copy()
            for handler in robot_handlers
        }

    def find_free_cell(self, robot_name: str, shelf_height: float) -> int:
        """Find best free cell matching shelf height."""
        if robot_name not in self.robot_cell_holdings:
            return -1

        occupied = self.get_occupied_cells(robot_name)
        free_indices = (i for i, is_occupied in enumerate(occupied) if not is_occupied)

        try:
            return min(
                free_indices,
                key=lambda i: abs(self.robot_cell_heights[robot_name][i] - shelf_height)
            )
        except ValueError:
            return -1  # No free cell

    def allocate_cell(self, robot_name: str, cell_index: int, request_uuid: str | None) -> None:
        """Mark cell as occupied by request."""
        if robot_name in self.robot_cell_holdings and 0 <= cell_index < len(self.robot_cell_holdings[robot_name]):
            self.robot_cell_holdings[robot_name][cell_index] = request_uuid

    def release_cell(self, robot_name: str, cell_index: int) -> None:
        """Mark cell as free."""
        if robot_name in self.robot_cell_holdings and 0 <= cell_index < len(self.robot_cell_holdings[robot_name]):
            self.robot_cell_holdings[robot_name][cell_index] = None

    def get_occupied_cells(self, robot_name: str) -> list[bool]:
        """Get list of which cells are occupied."""
        if robot_name not in self.robot_cell_holdings:
            return []

        return [cell is not None for cell in self.robot_cell_holdings[robot_name]]

    def find_cell_with_request(self, robot_name: str, request_uuid: str) -> int:
        """Find which cell holds a specific request."""
        if robot_name not in self.robot_cell_holdings:
            return -1

        try:
            return self.robot_cell_holdings[robot_name].index(request_uuid)
        except ValueError:
            return -1
