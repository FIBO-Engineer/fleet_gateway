import time
import redis.asyncio as redis
from roslibpy import ActionClient, Goal, GoalStatus, Ros, Message

class RobotHandler(Ros):
    def __init__(self, name: str, host_ip: str, port: int, cell_heights: list[int]) -> None:
        super().__init__(host=host_ip, port=port)
        self.run(1.0)
        self.name : str = name
        self.task_queue : list[Task] = []
        self.current_task : Task | None = None
        self.cell_heights : list[int] = cell_heights
        self.holding_totes : list[Request | None] = [None for _ in range(len(cell_heights))]
        # set up the action client and wait for server
        self.warehouse_cmd_action_client = ActionClient(
            self,
            '/warehouse_command',
            'warehouse_server/WarehouseCommandAction'
        )
    
    def find_free_cell(self, shelf_height: float) -> int:
        free_indices = (i for i, tote in enumerate(self.holding_totes) if tote is None)
        try:
            return min(free_indices, key=lambda i: abs(self.cell_heights[i] - shelf_height))
        except ValueError:
            return -1  # No free cell
        
    def find_storing_cell(self, delivery_id) -> int:
        for i in range(self.holding_totes.count):
            tote = self.holding_totes[i]
            if tote is not None and tote[1] == delivery_id:
                return i
        return -1

    # Should be called by a dispatcher
    def send_task(self, task: Task) -> None:
        if self.current_task is not None:
            raise RuntimeError("Current task in progress, cannot send new task")
        
        target_cell: int = -1
        match task.operation:
            case WarehouseOperation.TRAVEL:
                target_cell = -1

            case WarehouseOperation.PICKUP:
                target_cell = self.find_free_cell(task.nodes[-1].height)
                if target_cell == -1:
                    raise RuntimeError("No free cell is available for pickup")

            case WarehouseOperation.DELIVERY:
                target_cell = self.find_storing_cell(task.nodes[-1].node_id)
                if target_cell == -1:
                    raise RuntimeError("Item to deliver not found (delivery_id={delivery_id})")
                
        goal_msg = Message({
                    'nodes': task.nodes,
                    'operation': task.operation,
                    'robot_cell': target_cell
                    })

        goal = Goal(self.warehouse_cmd_action_client, goal_msg)
        
        def on_result(result):
            print(f"Result: {result}")
            results["result"] = result

        def on_feedback(feedback):
            print(f"Feedback: {feedback}")

        def on_error(error):
            print(f"Error: {error}")

        # Block until complete
        goal_id = self.warehouse_cmd_action_client.send_goal(goal, on_result, on_feedback, on_error)
        time.sleep(0.2)

        goal_id



    def cancel(self) -> None:
        if self.goal is not None and not self.reached:
            self.goal.cancel()
            self.reached = True
        else:
            raise RuntimeError("No goal to cancel")


    def has_reached(self) -> bool:
        return self.reached
