# Architecture Overview

## Development Phases
- Phase 0: Project Scaffold and Module Signatures
- Phase 1: Core Voice & Orchestration Pipeline
- Phase 2: Extensible Skill System and State Machine
- Phase 3: Advanced Wake Word Custom Models and Context Memory

## Coding Standards
- PEP 8 compliance.
- Google-style docstrings.
- Strict type hints on every signature.
- Subsystem boundaries must raise custom exceptions.

## Team Responsibilities
- Core Platform Team (2 devs): core/, config/, utils/
- Speech Team (2 devs): speech/, wakeword/
- LLM Team (1 dev): llm/
- Planner Team (1 dev): planner/
- Skills Team (2 devs): skills/

## Architectural Layers
- Interface / Presentation (main.py, CLI)
- Application Orchestration (core/)
- Domain Capabilities (skills/, llm/, planner/)
- Infrastructure (speech/, wakeword/, config/)

## Future Work
- GUI Widget Integration
- Vector Database Persistent Memory
- Cross-platform System Key Hooks
