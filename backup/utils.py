import math


def pose_msg(x, y, yaw):
    return {
        'position': {'x': x, 'y': y, 'z': 0.0},
        'orientation': {'x': 0.0, 'y': 0.0, 'z': math.sin(yaw/2), 'w': math.cos(yaw/2)}
    }
