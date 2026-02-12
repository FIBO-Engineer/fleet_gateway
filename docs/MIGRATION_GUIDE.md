# Migration Guide - Phase 1 Complete

## What Changed

### New Directory Structure

```
fleet_gateway/
├── config/                 # ✨ NEW - Configuration management
│   ├── __init__.py
│   ├── settings.py        # Pydantic settings
│   ├── robots.yaml        # Robot fleet config
│   └── robots_config.py   # YAML loader
│
├── docs/                   # ✨ NEW - Consolidated documentation
│   ├── ARCHITECTURE.md
│   ├── ROBOT_HANDLER.md   # Moved from root
│   └── DISPATCHER_GUIDE.md # Moved from root
│
├── examples/               # ✨ NEW - Example code
│   ├── __init__.py
│   └── basic_dispatcher.py # Was: fleet_gateway/dispatcher_example.py
│
├── tests/                  # ✨ NEW - Test structure (empty for now)
│   ├── __init__.py
│   ├── unit/
│   └── integration/
│
├── fleet_gateway/          # Package now has __init__.py
│   ├── __init__.py        # ✨ NEW
│   ├── enums.py
│   ├── models.py
│   ├── graph_oracle.py
│   └── robot_handler.py
│
├── .env.example            # ✨ NEW - Environment template
├── main.py                 # Unchanged
├── schema.py               # Unchanged
└── pubsub_helpers.py       # Unchanged
```

### Files Moved

| Old Location | New Location |
|--------------|--------------|
| `ROBOT_HANDLER.md` | `docs/ROBOT_HANDLER.md` |
| `DISPATCHER_GUIDE.md` | `docs/DISPATCHER_GUIDE.md` |
| `fleet_gateway/dispatcher_example.py` | `examples/basic_dispatcher.py` |

### Files Created

- `fleet_gateway/__init__.py` - Package initialization
- `config/settings.py` - Pydantic settings management
- `config/robots.yaml` - Robot fleet configuration
- `config/robots_config.py` - YAML configuration loader
- `.env.example` - Environment variable template
- `docs/ARCHITECTURE.md` - System architecture documentation
- All `__init__.py` files for proper package structure

### Import Fixes

**examples/basic_dispatcher.py**:
```python
# BEFORE (broken):
from robot_handler import RobotHandler

# AFTER (fixed):
from fleet_gateway.robot_handler import RobotHandler
```

## Breaking Changes

**None!** Phase 1 is fully backward compatible.

Existing code continues to work:
- `main.py` unchanged
- `schema.py` unchanged
- All imports still work
- API unchanged

## How to Use New Features

### 1. Configuration Management

**Create `.env` file** (copy from `.env.example`):
```bash
cp .env.example .env
# Edit .env with your values
```

**Use in code**:
```python
from config.settings import settings

print(settings.redis_host)
print(settings.supabase_url)
```

### 2. Robot Configuration

**Edit `config/robots.yaml`** to add/modify robots:
```yaml
robots:
  Lertvilai:
    host: "192.168.123.171"
    port: 8002
    cell_heights: [0.5, 1.0, 1.5]
```

**Load in code**:
```python
from config.robots_config import load_robots_config

robots = load_robots_config()
# robots = {'Lertvilai': {'host': '...', 'port': ..., ...}}
```

### 3. Run Examples

```bash
cd examples
python basic_dispatcher.py
```

### 4. Access Documentation

All docs now in `docs/`:
- `docs/ARCHITECTURE.md` - System overview
- `docs/ROBOT_HANDLER.md` - RobotHandler guide
- `docs/DISPATCHER_GUIDE.md` - Dispatcher usage

## Next Steps (Phase 2+)

Future phases will:
1. Split `schema.py` into separate files (queries, mutations, subscriptions)
2. Extract service layer from mutations
3. Create infrastructure abstraction layer
4. Add comprehensive tests

## Rollback (if needed)

If you need to rollback:
```bash
# Move docs back
mv docs/ROBOT_HANDLER.md .
mv docs/DISPATCHER_GUIDE.md .

# Move example back
mv examples/basic_dispatcher.py fleet_gateway/dispatcher_example.py

# Fix import in dispatcher_example.py
# Change: from fleet_gateway.robot_handler import RobotHandler
# To: from robot_handler import RobotHandler

# Remove new directories
rm -rf config docs examples tests
rm fleet_gateway/__init__.py
rm .env.example
```

## Testing

Verify everything still works:

```bash
# Start the server
uvicorn main:app --reload

# In another terminal, run example
cd examples
python basic_dispatcher.py
```

GraphQL should be available at: http://localhost:8000/graphql

## Notes

- Phase 1 focused on **structure** without breaking changes
- All existing code paths remain functional
- New structure enables cleaner organization in future phases
- Configuration is now centralized and type-safe
