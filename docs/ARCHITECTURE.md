# Fleet Gateway Architecture

## Overview

Fleet Gateway is a robot fleet management system that provides a GraphQL API for warehouse robot operations.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   GraphQL API Layer                         │
│            (FastAPI + Strawberry GraphQL)                   │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Queries  │  │ Mutations    │  │ Subscriptions│          │
│  └──────────┘  └──────────────┘  └──────────────┘          │
└────────────┬──────────────────────────────────┬──────────────┘
             │                                  │
    ┌────────▼────────┐              ┌─────────▼──────────┐
    │ Robot Handler   │              │ Graph Oracle       │
    │ (ROS + Redis)   │              │ (Supabase Path)    │
    └────────┬────────┘              └─────────┬──────────┘
             │                                  │
    ┌────────▼──────────────────────┬──────────▼─────────┐
    │                               │                    │
    │   ROS Communication          Redis (State)      Supabase
    │   (WarehouseCommand)         (Persistence)      (Graph Data)
    │
    └────────────────────────────────────────────────────┘
```

## Layers

### API Layer (schema.py)
- GraphQL schema definition with Strawberry
- Queries: robots, requests, robot, request
- Mutations: submit_assignments
- Subscriptions: robot_updates, request_updates
- Input/output type definitions

### Business Logic (fleet_gateway/)
- **RobotHandler**: ROS communication, job execution, state management
- **GraphOracle**: Path planning via Supabase database
- **Dispatcher Logic**: Request orchestration (in Mutation)

### Data Layer
- **Redis**: Robot state, request state, pub/sub
- **Supabase**: Warehouse graph, path planning (A* algorithm)

### Core Models (models.py, enums.py)
- Domain models: Node, Robot, Request, Job
- Enums: NodeType, RobotStatus, WarehouseOperation, RequestStatus

## Data Flow

### Request Submission Flow

```
1. User → GraphQL Mutation (submit_assignments)
2. Create requests in Redis
3. For each assignment:
   a. Get robot's current position
   b. Query GraphOracle for shortest path
   c. Get detailed node information
   d. Create Job with path nodes
   e. Send to RobotHandler
4. RobotHandler → ROS WarehouseCommand action
5. Robot executes job
6. Feedback → Update Redis → Publish update
7. Subscriptions receive real-time updates
```

### Robot State Updates

```
1. ROS Topic → RobotHandler callback
2. Update internal state
3. Persist to Redis (_persist_to_redis)
4. Publish notification (_publish_update)
5. GraphQL subscribers receive update
```

## Key Components

### RobotHandler
- Extends roslibpy.Ros for ROS connectivity
- Manages job queue and execution
- Tracks cell holdings (what request is in which cell)
- Persists state to Redis
- Publishes updates for subscriptions

### GraphOracle
- Interface to Supabase database
- Path planning using A* algorithm
- Node information retrieval
- Graph-based warehouse navigation

### Redis Schema

**Robot State**:
```
robot:{name} (hash)
  - name
  - robot_cell_heights (JSON array)
  - robot_status (int)
  - mobile_base_state (JSON)
  - piggyback_state (JSON)
  - current_job (JSON)
  - jobs (JSON array)
```

**Request State**:
```
request:{uuid} (hash)
  - uuid
  - pickup (JSON)
  - delivery (JSON)
  - handler (robot name)
  - request_status (int)
```

**Pub/Sub Channels**:
```
robot:{name}:update
request:{uuid}:update
```

## Operation Types

1. **TRAVEL** (0): Move through waypoints, no cell interaction
2. **PICKUP** (1): Pick item from shelf into robot cell
3. **DELIVERY** (2): Deliver item from robot cell to depot

## Robot Status States

- **OFFLINE** (0): Not connected
- **IDLE** (1): Ready for jobs
- **INACTIVE** (2): Manually disabled by user
- **BUSY** (3): Executing a job
- **ERROR** (4): Job failed

## Request Status States

- **CANCELLED** (0): User cancelled
- **FAILED** (1): Execution failed
- **IN_PROGRESS** (2): Currently executing
- **COMPLETED** (3): Successfully finished

## Technologies

- **FastAPI**: Web framework
- **Strawberry GraphQL**: GraphQL schema and API
- **Redis**: State persistence and pub/sub
- **Supabase**: PostgreSQL database with RPC functions
- **roslibpy**: ROS bridge over WebSocket
- **Pydantic**: Configuration and validation

## Configuration

- `.env`: Environment variables (Redis, Supabase, server)
- `config/robots.yaml`: Robot fleet configuration
- `config/settings.py`: Pydantic settings management

## Scalability Considerations

- **Horizontal scaling**: Can run multiple API instances (stateless)
- **Redis bottleneck**: Single Redis instance for now
- **Robot limit**: One RobotHandler per robot, memory-bound
- **GraphOracle**: Single connection, could pool
- **Pub/sub**: Redis pub/sub scales well for subscriptions

## Future Enhancements

- [ ] Connection pooling for GraphOracle
- [ ] Redis Cluster for high availability
- [ ] Job scheduling/prioritization algorithms
- [ ] Collision detection between robots
- [ ] Battery level monitoring
- [ ] Performance metrics and logging
- [ ] Authentication and authorization
