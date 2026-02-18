# Dispatcher System Guide

## Overview

The dispatcher system allows you to submit high-level warehouse requests and robot assignments. The system automatically:
1. Computes shortest paths using `graph_oracle`
2. Creates jobs with full path nodes
3. Sends jobs to robots
4. Tracks requests in Redis
5. Triggers GraphQL subscriptions

## Architecture

```
User Input (GraphQL Mutation)
    ↓
[requests: pickup/delivery pairs]
[assignments: robot + target nodes]
    ↓
Dispatcher (Mutation.submit_assignments)
    ↓
For each target node:
  - Query graph_oracle.getShortestPathById()
  - Get full node details
  - Create Job with path
  - Determine operation (TRAVEL/PICKUP/DELIVERY)
    ↓
RobotHandler.send_job()
    ↓
Robot executes via ROS WarehouseCommand action
```

## GraphQL Mutation

### Input Types

**RequestInput**:
```graphql
input RequestInput {
  pickupId: Int!      # Node ID of shelf to pick from
  deliveryId: Int!    # Node ID of depot to deliver to
}
```

**AssignmentInput**:
```graphql
input AssignmentInput {
  robot: String!       # Name of the robot
  jobs: [Int!]!        # List of target node IDs in order
}
```

### Mutation

```graphql
mutation {
  submitAssignments(
    requests: [
      {pickupId: 20, deliveryId: 40}
      {pickupId: 25, deliveryId: 45}
    ]
    assignments: [
      {
        robot: "Lertvilai"
        jobs: [20, 40]  # Visit shelf 20, then depot 40
      }
      {
        robot: "Chompu"
        jobs: [25, 45]  # Visit shelf 25, then depot 45
      }
    ]
  ) {
    success
    message
    requestUuids
  }
}
```

## How It Works

### 1. Path Computation

For each target node in `jobs`, the system:

```python
# Get robot's current position
current_node_id = robot.mobile_base_state.last_seen.id

# Query shortest path
path_node_ids = graph_oracle.getShortestPathById(
    graph_id,      # From environment variable
    current_node_id,  # Robot's current position
    target_node_id    # Where robot needs to go
)

# Get full node details (x, y, height, etc.)
path_nodes = graph_oracle.getNodesByIds(graph_id, path_node_ids)
```

### 2. Operation Detection

The system automatically determines the operation type:

- **PICKUP**: If `target_node_id` matches a `pickupId` in requests
- **DELIVERY**: If `target_node_id` matches a `deliveryId` in requests
- **TRAVEL**: Otherwise (just moving between waypoints)

### 3. Job Creation

```python
job = {
    'operation': WarehouseOperation.PICKUP.value,  # 0, 1, or 2
    'nodes': [
        {
            'id': 10,
            'alias': 'W1',
            'x': 0.0,
            'y': 0.0,
            'height': 0.0,
            'node_type': 0  # WAYPOINT
        },
        {
            'id': 20,
            'alias': 'S1',
            'x': 5.0,
            'y': 5.0,
            'height': 1.0,
            'node_type': 2  # SHELF
        }
    ],
    'request_uuid': '123e4567-...'  # If PICKUP/DELIVERY
}
```

### 4. Job Execution

- If robot is **IDLE**: Job sent immediately
- If robot is **BUSY**: Job queued, executes after current job completes
- Robot uses `request_uuid` to track which cell holds which request

## Example Scenarios

### Scenario 1: Simple Pickup and Delivery

```graphql
mutation {
  submitAssignments(
    requests: [{pickupId: 100, deliveryId: 200}]
    assignments: [{
      robot: "Lertvilai"
      jobs: [100, 200]
    }]
  ) {
    success
    message
    requestUuids
  }
}
```

**What happens**:
1. System computes path from robot's position → node 100
2. Creates PICKUP job with that path
3. Sends to robot, stores request UUID in cell
4. When pickup completes, computes path 100 → 200
5. Creates DELIVERY job with that path
6. Robot delivers from cell to depot

### Scenario 2: Multiple Requests, One Robot

```graphql
mutation {
  submitAssignments(
    requests: [
      {pickupId: 100, deliveryId: 200}
      {pickupId: 150, deliveryId: 250}
    ]
    assignments: [{
      robot: "Lertvilai"
      jobs: [100, 200, 150, 250]
    }]
  ) {
    success
    message
    requestUuids
  }
}
```

**What happens**:
1. Pickup from 100 → deliver to 200 (request 1 complete)
2. Pickup from 150 → deliver to 250 (request 2 complete)

### Scenario 3: Travel Job (No Pickup/Delivery)

```graphql
mutation {
  submitAssignments(
    requests: []  # No requests
    assignments: [{
      robot: "Lertvilai"
      jobs: [10, 20, 30]  # Just waypoints
    }]
  ) {
    success
    message
    requestUuids
  }
}
```

**What happens**:
- Robot travels through waypoints 10 → 20 → 30
- No cell interaction (TRAVEL operations)

### Scenario 4: Multiple Robots, Parallel Execution

```graphql
mutation {
  submitAssignments(
    requests: [
      {pickupId: 100, deliveryId: 200}
      {pickupId: 150, deliveryId: 250}
    ]
    assignments: [
      {robot: "Lertvilai", jobs: [100, 200]}
      {robot: "Chompu", jobs: [150, 250]}
    ]
  ) {
    success
    message
    requestUuids
  }
}
```

**What happens**:
- Both robots work in parallel
- Lertvilai handles request 1
- Chompu handles request 2

## Monitoring

### Subscribe to Robot Updates

```graphql
subscription {
  robotUpdates(name: "Lertvilai") {
    name
    robotStatus
    currentJob {
      operation
      nodes { id }
    }
    holdings {
      uuid
      requestStatus
    }
  }
}
```

### Subscribe to Request Updates

```graphql
subscription {
  requestUpdates(uuid: "123e4567-...") {
    uuid
    requestStatus
    handler {
      name
      robotStatus
    }
  }
}
```

## Error Handling

The mutation returns `SubmitResult`:

```typescript
{
  success: boolean
  message: string
  requestUuids: string[]  // UUIDs of created requests
}
```

**Common errors**:
- Robot not found
- Robot state not in Redis
- Graph path computation failed
- No free cell for pickup

## Environment Variables

Required in `.env` or environment:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
GRAPH_ID=1  # Which graph to use for pathfinding
```

## Database Requirements

The Supabase database must have these RPC functions:
- `wh_astar_shortest_path` - Computes shortest path between nodes
- `wh_get_nodes_by_ids` - Fetches detailed node information

See the path network schema in the database documentation.
