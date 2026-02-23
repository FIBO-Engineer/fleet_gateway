from __future__ import annotations


def test_runtime_types_available_in_robot_module():
    """
    Verifies the circular dependency fix for robot.py.

    Previously, MobileBaseState, Pose, Tag, PiggybackState, and RobotCell were
    only imported under TYPE_CHECKING to avoid the circular chain:

        types.py -> type_resolvers.py -> fleet_handler.py -> robot.py -> types.py

    This caused a NameError at runtime whenever RobotConnector was instantiated.

    The fix imports these types from fleet_gateway.models (a dependency-free
    plain-dataclass module) at runtime, breaking the circular chain.
    """
    import fleet_gateway.robot as robot_module
    from fleet_gateway import models

    for name, expected in [
        ("MobileBaseState", models.MobileBaseState),
        ("Pose",            models.Pose),
        ("Tag",             models.Tag),
        ("PiggybackState",  models.PiggybackState),
        ("RobotCell",       models.RobotCell),
    ]:
        assert hasattr(robot_module, name), \
            f"{name} is not available at runtime in robot.py"
        assert getattr(robot_module, name) is expected, \
            f"robot.py.{name} should be the plain dataclass from models.py, not the strawberry type"
