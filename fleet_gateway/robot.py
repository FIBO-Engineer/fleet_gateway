import roslibpy
import roslibpy.actionlib
from typing import Optional


class Robot(roslibpy.Ros):
    def __init__(self, name: str, host_ip: str, port: int) -> None:
        super().__init__(host=host_ip, port=port)
        self.run(1.0)
        self.name = name
        self.reached = True
        # set up the action client and wait for server
        self.move_base_action_client = roslibpy.actionlib.ActionClient(
            self,
            '/move_base',
            'move_base_msgs/MoveBaseAction'
        )
        # if self.move_base_action_client.wait_for_server(timeout=5.0):
        #     print(f"{self.name}: action server ready")
        # else:
        #     print(f"{self.name}: no action server")
        self.goal: Optional[roslibpy.actionlib.Goal] = None

    def navigate(self, pose: dict, frame_id: str = 'map') -> None:
        """
        pose should be a dict:
        {
            'position':    {'x': x, 'y': y, 'z': 0.0},
            'orientation': {'x': ox, 'y': oy, 'z': oz, 'w': ow}
        }
        """
        if self.goal is not None and not self.reached:
            self.goal.cancel()

        # mark in-flight
        self.reached = False

        # Construct a PoseStamped inside a MoveBaseGoal
        goal_msg = roslibpy.Message({
            'target_pose': {
                'header': {
                    'stamp': {'secs': 0, 'nsecs': 0},
                    'frame_id': frame_id
                },
                'pose': pose
            }
        })

        self.goal = roslibpy.actionlib.Goal(self.move_base_action_client, goal_msg)

        # when the action returns a result, mark as reached
        def _on_result(result):
            # result is a MoveBaseResult message
            self.reached = True
            print(f"{self.name}: navigation complete → {result}")
            # self.move_base_action_client.dispose() # Don't

        self.goal.on('result', _on_result)
        self.goal.send()

    def cancel(self) -> None:
        if self.goal is not None and not self.reached:
            self.goal.cancel()
            self.reached = True
        else:
            raise RuntimeError("No goal to cancel")


    def has_reached(self) -> bool:
        return self.reached
