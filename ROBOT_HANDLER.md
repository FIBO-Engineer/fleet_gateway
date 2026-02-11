# RobotHandler Implementation

## Overview

The `RobotHandler` class acts as a controller that:
1. Communicates with a robot via ROS `WarehouseCommand` action
2. Maintains robot state in Redis
3. Triggers GraphQL subscriptions on state changes
4. Manages job queuing and execution

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────┐
│   FastAPI   │────────▶│ RobotHandler │◀───────▶│  Robot  │
│  + GraphQL  │         │              │   ROS   │         │
└─────────────┘         └──────────────┘         └─────────┘
      │                        │
      │                        │
      ▼                        ▼
┌─────────────────────────────────┐
│            Redis                │
│  - Robot state (hashes)         │
│  - Request state (hashes)       │
│  - Pub/Sub for subscriptions    │
└─────────────────────────────────┘
```

## Key Features

### 1. Redis Bookkeeping

All robot state is persisted to Redis as a hash at key `robot:{name}`:

```python
{
    'name': 'Lertvilai',
    'robot_cell_heights': '[0.5, 1.0, 1.5]',
    'robot_status': '1',  # IDLE
    'mobile_base_status': '{"last_seen": {...}, "x": 0.0, "y": 0.0, "a": 0.0}',
    'piggyback_state': '{"axis_0": 0.0, "axis_1": 0.0, "axis_2": 0.0, "gripper": false}',
    'current_job': '{"operation": 1, "nodes": [...]}',
    'jobs': '[...]'
}
```

### 2. Job Execution Flow

1. **Send Job**: `await robot_handler.send_job(job, request_uuid)`
2. **Goal Creation**: Converts job to ROS WarehouseCommand goal message
3. **Cell Selection**: Automatically selects appropriate robot cell
4. **Callbacks**: Registers result, feedback, and error handlers
5. **State Updates**: Updates Redis and publishes to subscriptions
6. **Queue Processing**: Automatically processes queued jobs on completion

### 3. Operation Types

- **TRAVEL (0)**: Move through waypoints, no cell interaction
- **PICKUP (1)**: Pick up item from shelf into robot cell
- **DELIVERY (2)**: Deliver item from robot cell to depot

### 4. Cell Management

The robot has multiple cells (storage compartments) with different heights:

```python
cell_heights = [0.5, 1.0, 1.5]  # Heights in meters
```

- **PICKUP**: Finds best free cell matching shelf height
- **DELIVERY**: Finds cell containing the item to deliver
- Tracks which request UUID is in each cell

### 5. State Tracking

**Robot Status**:
- `0` - OFFLINE
- `1` - IDLE
- `2` - INACTIVE (error state)
- `3` - BUSY (executing job)

**Request Status** (stored separately in Redis):
- `0` - CANCELLED
- `1` - FAILED
- `2` - IN_PROGRESS
- `3` - COMPLETED

## Usage Examples

### Initialize Robot Handler

```python
robot = RobotHandler(
    name='Lertvilai',
    host_ip='192.168.123.171',
    port=8002,
    cell_heights=[0.5, 1.0, 1.5],
    redis_client=redis_client
)
await robot.initialize_in_redis()
```

### Send a Travel Job

```python
travel_job = {
    'operation': 0,  # TRAVEL
    'nodes': [
        {'id': 1, 'x': 0.0, 'y': 0.0, 'node_type': 0},
        {'id': 2, 'x': 5.0, 'y': 5.0, 'node_type': 0}
    ]
}
await robot.send_job(travel_job)
```

### Send Pickup Request

```python
pickup_job = {
    'operation': 1,  # PICKUP
    'nodes': [
        {'id': 10, 'x': 0.0, 'y': 0.0, 'node_type': 0},  # Waypoint
        {'id': 20, 'x': 5.0, 'y': 5.0, 'height': 1.0, 'node_type': 2}  # Shelf
    ]
}
await robot.send_job(pickup_job, request_uuid='123e4567-...')
```

### Cancel Current Job

```python
await robot.cancel_current_job()
```

## Bug Fixes

The following issues were fixed in the original implementation:

1. ✅ **Fixed undefined types**: Added proper imports for types
2. ✅ **Fixed `len()` usage**: Changed `self.holding_totes.count` to `len(self.holding_totes)`
3. ✅ **Fixed UUID tracking**: Changed from tuple access to UUID string storage
4. ✅ **Fixed attribute access**: Changed `node.node_id` to `node['id']`
5. ✅ **Fixed undefined variables**: Removed reference to undefined `results` dict
6. ✅ **Fixed goal tracking**: Added proper `current_goal` attribute
7. ✅ **Added async/await**: Made all Redis operations async
8. ✅ **Added Redis bookkeeping**: Implemented `_persist_to_redis()`
9. ✅ **Added subscription updates**: Implemented `_publish_update()`
10. ✅ **Added proper callbacks**: Implemented async result/feedback/error handlers
11. ✅ **Added state management**: Proper tracking of robot and job state
12. ✅ **Added ROS topic subscribers**: Subscribe to robot state topics

## GraphQL Integration

The RobotHandler integrates with GraphQL subscriptions:

```graphql
subscription {
  robotUpdates(name: "Lertvilai") {
    name
    robotStatus
    currentJob {
      operation
      nodes {
        id
        x
        y
      }
    }
    holdings {
      uuid
      requestStatus
    }
  }
}
```

When robot state changes, `_publish_update()` triggers the subscription.

## Error Handling

- **No free cell**: Raises `RuntimeError` if PICKUP requested but all cells occupied
- **Item not found**: Raises `RuntimeError` if DELIVERY requested but item not in any cell
- **Job in progress**: Raises `RuntimeError` if trying to send job while another is executing
- **ROS errors**: Captured in `_on_job_error()`, sets status to INACTIVE

## Future Enhancements

- [ ] Add retry logic for failed jobs
- [ ] Implement job priority queue
- [ ] Add collision detection/avoidance coordination
- [ ] Add battery level monitoring
- [ ] Add performance metrics (job completion time, etc.)
- [ ] Add job scheduling algorithm
