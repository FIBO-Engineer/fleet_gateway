# Fleet Gateway ROS API Examples

This directory contains sample ROS message, service, and action definitions for the Fleet Gateway system.

## Overview

The Fleet Gateway uses ROS communication to manage warehouse operations, including:
- Graph representation of the warehouse layout
- Command execution for robot operations (pickup/delivery)
- Node-based navigation system

## Message Definitions

### Node.msg

Represents a node in the warehouse graph.

**Fields:**
- `uint64 id` - Unique identifier for the node
- `string alias` - Human-readable name
- `float64 x` - X coordinate position (meters)
- `float64 y` - Y coordinate position (meters)
- `float64 height` - Height/Z coordinate (meters)
- `uint8 node_type` - Type of node (see enum below)

**Node Type Enum:**
- `WAYPOINT = 0` - Navigation waypoint
- `CONVEYOR = 1` - Conveyor belt location
- `SHELF = 2` - Storage shelf location
- `CELL = 3` - Cell/slot location
- `DEPOT = 4` - Robot charging/parking depot

**Example Messages:**
```yaml
# Shelf node
id: 101
alias: "shelf_A1"
x: 5.5
y: 3.2
height: 0.0
node_type: 2  # SHELF

---
# Waypoint node
id: 200
alias: "intersection_1"
x: 2.0
y: 1.5
height: 0.0
node_type: 0  # WAYPOINT

---
# Depot node
id: 1
alias: "depot_01"
x: 0.0
y: 0.0
height: 0.0
node_type: 4  # DEPOT

---
# Conveyor node
id: 300
alias: "conveyor_main"
x: 8.5
y: 4.0
height: 0.5
node_type: 1  # CONVEYOR
```

## Service Definitions

### SetGraph.srv

Service to configure the warehouse graph topology.

**Request:**
- `Node[] nodes` - Array of nodes defining the warehouse layout

**Response:**
- `bool success` - Whether the graph was successfully set
- `string message` - Status or error message

**Example Request:**
```yaml
nodes:
  - id: 1
    alias: "depot_01"
    x: 0.0
    y: 0.0
    height: 0.0
    node_type: 4  # DEPOT
  - id: 2
    alias: "wp_entrance"
    x: 2.0
    y: 0.0
    height: 0.0
    node_type: 0  # WAYPOINT
  - id: 3
    alias: "shelf_A1"
    x: 5.0
    y: 3.0
    height: 0.0
    node_type: 2  # SHELF
  - id: 4
    alias: "conveyor_01"
    x: 8.0
    y: 1.0
    height: 0.5
    node_type: 1  # CONVEYOR
```

**Example Response (Success):**
```yaml
success: true
message: "Graph configured with 4 nodes"
```

**Example Response (Failure):**
```yaml
success: false
message: "Invalid node configuration: duplicate node ID 3"
```

## Action Definitions

### WarehouseCommand.action

Full-featured action for executing warehouse operations with complete node information.

**Goal:**
- `Node[] nodes` - Sequence of nodes to visit
- `uint8 operation` - Operation type (PICKUP=0, DELIVERY=1)
- `uint8 robot_cell` - Robot cell/slot to use (LOWEST=0)

**Feedback:**
- `uint64 detected_id` - Currently detected/visited node ID
- `uint8 state` - Current execution state

**Result:**
- `uint64 detected_id` - Final detected node ID
- `uint8 state` - Final execution state

**Example Goal (PICKUP Operation):**
```yaml
nodes:
  - id: 1
    alias: "depot_01"
    x: 0.0
    y: 0.0
    height: 0.0
    node_type: 4  # DEPOT
  - id: 2
    alias: "wp_1"
    x: 2.5
    y: 1.5
    height: 0.0
    node_type: 0  # WAYPOINT
  - id: 3
    alias: "shelf_A1"
    x: 5.0
    y: 3.0
    height: 0.0
    node_type: 2  # SHELF
operation: 0  # PICKUP
robot_cell: 0  # LOWEST
```

**Example Feedback:**
```yaml
detected_id: 2
state: 1  # Currently at waypoint
```

**Example Result:**
```yaml
detected_id: 3
state: 2  # Completed at shelf
```

### WarehouseCommand.simple.action

Simplified action using node IDs instead of full node definitions. Assumes the graph has been pre-configured using SetGraph service.

**Goal:**
- `uint64[] nodes` - Sequence of node IDs to visit
- `uint8 operation` - Operation type (PICKUP=0, DELIVERY=1)
- `uint8 robot_cell` - Robot cell/slot to use (LOWEST=0)

**Feedback:**
- `uint64 detected_id` - Currently detected/visited node ID
- `uint8 state` - Current execution state

**Result:**
- `uint64 detected_id` - Final detected node ID
- `uint8 state` - Final execution state

**Example Goal (DELIVERY Operation):**
```yaml
nodes: [1, 2, 3, 4]  # depot -> wp1 -> shelf -> conveyor
operation: 1  # DELIVERY
robot_cell: 0  # LOWEST
```

**Example Feedback:**
```yaml
detected_id: 2
state: 1  # Currently at node 2
```

**Example Result:**
```yaml
detected_id: 4
state: 3  # Completed delivery at node 4
```

## Complete Workflow Example

### Step 1: Configure Warehouse Graph

**Service:** `/fleet/set_graph` (SetGraph)

**Request:**
```yaml
nodes:
  - id: 1
    alias: "depot_01"
    x: 0.0
    y: 0.0
    height: 0.0
    node_type: 4
  - id: 2
    alias: "wp_entrance"
    x: 2.0
    y: 0.0
    height: 0.0
    node_type: 0
  - id: 3
    alias: "wp_central"
    x: 5.0
    y: 2.0
    height: 0.0
    node_type: 0
  - id: 4
    alias: "shelf_A1"
    x: 7.0
    y: 3.0
    height: 0.0
    node_type: 2
  - id: 5
    alias: "shelf_A2"
    x: 7.0
    y: 5.0
    height: 0.0
    node_type: 2
  - id: 6
    alias: "conveyor_out"
    x: 10.0
    y: 2.0
    height: 0.5
    node_type: 1
```

**Response:**
```yaml
success: true
message: "Warehouse graph configured with 6 nodes"
```

### Step 2: Execute Pickup Operation

**Action:** `/warehouse_command_simple` (WarehouseCommandSimple)

**Goal:**
```yaml
nodes: [1, 2, 3, 4]  # depot -> entrance -> central -> shelf_A1
operation: 0  # PICKUP
robot_cell: 0  # LOWEST
```

**Feedback Stream:**
```yaml
# Feedback 1
detected_id: 1
state: 0

# Feedback 2
detected_id: 2
state: 1

# Feedback 3
detected_id: 3
state: 1

# Feedback 4
detected_id: 4
state: 2
```

**Result:**
```yaml
detected_id: 4
state: 2  # Pickup completed
```

### Step 3: Execute Delivery Operation

**Goal:**
```yaml
nodes: [4, 3, 6]  # shelf_A1 -> central -> conveyor
operation: 1  # DELIVERY
robot_cell: 0  # LOWEST
```

**Feedback Stream:**
```yaml
# Feedback 1
detected_id: 4
state: 0

# Feedback 2
detected_id: 3
state: 1

# Feedback 3
detected_id: 6
state: 3
```

**Result:**
```yaml
detected_id: 6
state: 3  # Delivery completed
```

## Usage Notes

1. **Graph Setup**: Always call `SetGraph` service before executing warehouse commands to ensure the system knows the warehouse layout.

2. **Node IDs**: Node IDs must be unique across the warehouse. It's recommended to use a numbering scheme (e.g., 1-99 for depots, 100-199 for waypoints, etc.).

3. **Operation Types**:
   - `PICKUP = 0`: Robot picks up items from a location
   - `DELIVERY = 1`: Robot delivers items to a location

4. **Robot Cell**:
   - `LOWEST = 0`: Use the lowest available cell/slot on the robot

5. **Action Choice**:
   - Use `WarehouseCommand.action` when you need to send full node information with coordinates
   - Use `WarehouseCommand.simple.action` when the graph is pre-configured and you only need to specify node IDs (more efficient)

6. **State Values** (implementation-specific):
   - `0`: Idle/Starting
   - `1`: Moving/In Transit
   - `2`: Pickup Completed
   - `3`: Delivery Completed

## ROS Interface Summary

**Services:**
- `/fleet/set_graph` (SetGraph) - Configure warehouse graph

**Actions:**
- `/warehouse_command` (WarehouseCommand) - Execute commands with full node data
- `/warehouse_command_simple` (WarehouseCommandSimple) - Execute commands with node IDs only
