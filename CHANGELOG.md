# Changelog

All notable changes to the Fleet Gateway project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.2.0] - Phase 2: API Layer Refactor

### Changed
- **BREAKING (Internal)**: Split monolithic `schema.py` (564 lines) into modular API package
- Reorganized GraphQL layer into separate concerns:
  - `fleet_gateway/api/types.py` - Type definitions
  - `fleet_gateway/api/deserializers.py` - Data conversion
  - `fleet_gateway/api/queries.py` - Query resolvers
  - `fleet_gateway/api/mutations.py` - Mutation resolvers
  - `fleet_gateway/api/subscriptions.py` - Subscription resolvers
  - `fleet_gateway/api/schema.py` - Combined schema
- Updated `main.py` to import from new API package

### Added
- Comprehensive docstrings for all API functions
- Better separation of concerns in API layer

### Removed
- Monolithic `schema.py` (moved to `schema_old.py` backup, later deleted)

### Notes
- **Zero API breaking changes** - All GraphQL operations work identically
- Better maintainability and testability
- Easier for teams to collaborate on different components

## [0.1.0] - Phase 1: Foundation & Organization

### Added
- **Configuration management** system:
  - `config/settings.py` - Pydantic-based settings with type safety
  - `config/robots.yaml` - YAML-based robot fleet configuration
  - `config/robots_config.py` - YAML loader utility
  - `.env.example` - Environment variable template
- **Documentation hub** in `docs/`:
  - `ARCHITECTURE.md` - System architecture overview
  - `MIGRATION_GUIDE.md` - Migration instructions
  - Moved existing guides to docs/
- **Examples directory** with fixed imports:
  - Moved `dispatcher_example.py` → `examples/basic_dispatcher.py`
  - Fixed broken import from `robot_handler` to `fleet_gateway.robot_handler`
- **Test infrastructure**:
  - `tests/unit/` - Unit test structure
  - `tests/integration/` - Integration test structure
- **Package structure**:
  - Added `__init__.py` to all packages for proper Python package structure
  - `fleet_gateway/__init__.py` with version and description
- **Dependencies**:
  - `pydantic-settings>=2.0.0` for configuration
  - `pyyaml>=6.0` for YAML config files
- **requirements.txt** with all project dependencies

### Changed
- Reorganized project structure with clear separation of concerns
- Professional directory layout following Python best practices

### Fixed
- Import error in dispatcher example (broken path)

### Notes
- **Zero breaking changes** - All existing code works unchanged
- Backward compatible with previous setup
- Optional configuration system (existing hardcoded values still work)

## [0.0.1] - Initial Implementation

### Added
- Core fleet management system with:
  - GraphQL API (FastAPI + Strawberry)
  - ROS robot communication via `robot_handler.py`
  - Path planning via Supabase (`graph_oracle.py`)
  - Redis-based state management
  - Real-time subscriptions for robot and request updates
- Domain models:
  - `enums.py` - Shared enumerations
  - `models.py` - Data models (Node, Robot, Request, Job, etc.)
- GraphQL operations:
  - Queries: `robots`, `requests`, `robot(name)`, `request(uuid)`
  - Mutations: `submit_assignments`
  - Subscriptions: `robot_updates`, `request_updates`
- RobotHandler features:
  - ROS communication via WebSocket
  - Job queueing and execution
  - Cell management for warehouse operations
  - State persistence to Redis
- Documentation:
  - `ROBOT_HANDLER.md` - Robot handler guide
  - `DISPATCHER_GUIDE.md` - Dispatcher usage guide

---

## Version History Summary

- **v0.2.0**: API layer refactored into modular package
- **v0.1.0**: Added configuration, documentation, and project structure
- **v0.0.1**: Initial working implementation

## Migration Guides

- See `docs/MIGRATION_GUIDE.md` for Phase 1 changes
- See `docs/PHASE2_COMPLETE.md` for Phase 2 changes
