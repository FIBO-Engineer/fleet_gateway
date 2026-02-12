"""
Robot fleet configuration loader.

Reads robot configuration from robots.yaml file.
"""

import yaml
from pathlib import Path
from typing import TypedDict


class RobotConfigDict(TypedDict):
    """Type definition for robot configuration"""
    host: str
    port: int
    cell_heights: list[float]


def load_robots_config(config_path: str | None = None) -> dict[str, RobotConfigDict]:
    """
    Load robot configuration from YAML file.

    Args:
        config_path: Path to robots.yaml. If None, uses default location.

    Returns:
        Dictionary mapping robot names to their configurations
    """
    if config_path is None:
        # Default to config/robots.yaml
        config_dir = Path(__file__).parent
        config_path = config_dir / "robots.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Robot configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    return config.get('robots', {})
