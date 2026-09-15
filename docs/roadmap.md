# Development Roadmap

## Phase 0: Architecture and Scaffold
- Establish project directory structure.
- Define interfaces and class signatures.
- Set up unit testing templates and configuration schemas.

## Phase 1: Core Pipeline Integration
- Integrate Speech-to-Text and Text-to-Speech engines.
- Connect NVIDIA NIM LLM client interface.
- Implement Orchestrator pipeline loop.

## Phase 2: Wake Word & Basic Skills
- Implement WakeWordDetector stream listener.
- Set up SkillManager and load custom skills.
- Add simple tasks (tell time, open apps, system information).

## Phase 3: Advanced Skills & Models
- Implement custom ONNX wake word model.
- Extend planner with multi-step DAG resolving capabilities.
- Integrate context history memory.
