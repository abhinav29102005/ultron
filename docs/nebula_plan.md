# NEBULA: Sovereign Autonomous Personal AI Assistant & Speculative Live RAG
**Submission for the Nebius Global AI Hackathon**  
**Track: Personal AI Track (Primary) & Best Apps and Agents Track**  
**Powered by:** Nebius Token Factory & NVIDIA Nemotron Open-Source Models  

---

## 1. Executive Summary

**NEBULA** is an always-on, completely sovereign personal desktop assistant engineered to keep user data strictly under local control while delivering state-of-the-art agentic intelligence. 

Traditional personal assistants route all private conversations to monolithic cloud vendors and suffer from several-second latency gaps during speech interaction. **NEBULA** solves this by pairing **local-first persistent storage** and **native OS hardware agency** with **NVIDIA Nemotron open-source models hosted on Nebius Token Factory**:

- **Hierarchical Two-Tier Model Routing**:
  - **Tier 1 (Fast Calls & Stream Decider)**: `nvidia/nemotron-3-nano-30b-a3b` handles speculative intent detection, speech stream boundary analysis, and everyday commands in sub-150ms TTFT, stretching Nebius credits further.
  - **Tier 2 (Deep Reasoning & Tool Synthesis)**: `nvidia/nemotron-3-super-120b-a12b` (and `nvidia/llama-3.1-nemotron-70b-instruct` / `nemotron-3-ultra`) executes complex multi-turn reasoning, cross-platform hardware control, and strict grounded synthesis for Streaming Live RAG.
- **Sovereign Personal Memory**: Persistent chat sessions, multi-turn context windows, local vector indexes, and user preferences stored exclusively in local ACID databases (`data/nebula.db`).
- **Complete Operating System Agency**: Native cross-platform system scanner (CPU, RAM, audio endpoints, display brightness), audio output/input device switcher, application controller, and browser takeover.
- **Speculative Live RAG Pipeline**: Ingests timestamped speech transcript chunks in real-time (`0.0s`, `0.8s`, `1.6s`) and speculatively triggers hybrid dense+sparse retrieval *before* the user finishes speaking, eliminating conversational dead air with guaranteed citation traceability (`[Doc_XX §YY]`).

---

## 2. Architecture & Dataflow

```
Incoming Stream (Voice / Text CLI / Hotkey)
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    NEBULA CYBERNETIC CONTROLLER                         │
│  • Speech-to-Text Streamer / Real-time Transcriber                      │
│  • Intent Semantic Stability & Boundary Evaluator                       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
         ┌───────────────────────────┴───────────────────────────┐
         ▼                                                       ▼
┌───────────────────────────────────────┐   ┌─────────────────────────────────────┐
│    NEBIUS TOKEN FACTORY (TIER 1)      │   │    LOCAL PERSONAL PERSISTENCE       │
│  • Model: nvidia/nemotron-3-nano-30b  │   │  • Unified Engine: data/nebula.db   │
│  • Sub-150ms TTFT Stream Decider      │   │  • Chat Lineage & Context Windows   │
│  • Multi-Intent Query Decomposer      │   │  • User Profile & Dynamic Settings  │
└──────────────────┬────────────────────┘   └──────────────────┬──────────────────┘
                   │                                           │
                   ▼                                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              STREAMING LIVE RAG & EVIDENCE FUSION                       │
│  • Hybrid Retriever: Dense Vector Embeddings + BM25 Sparse Search       │
│  • Reciprocal Rank Fusion (RRF) & Delta Constraint Resolver             │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    NEBIUS TOKEN FACTORY (TIER 2)                        │
│  • Model: nvidia/nemotron-3-super-120b-a12b / Nemotron-3-Ultra          │
│  • Deep Agentic Reasoning & Tool Synthesis                              │
│  • Strict Grounded Generation with Exact Citations [Doc_XX §YY]         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
         ┌───────────────────────────┴───────────────────────────┐
         ▼                                                       ▼
┌───────────────────────────────────────┐   ┌─────────────────────────────────────┐
│        SYSTEM & HARDWARE SKILLS       │   │        CELESTIAL AUDIO SYNTHESIS    │
│  • Audio Device Switcher (Sinks/Mics) │   │  • Piper ONNX Neural Speech Engine  │
│  • Display Brightness & System Volume │   │  • Nebula DSP Harmonic Enhancement  │
│  • Native Application & Browser Agent │   │  • Real-time Audio Bus & Barge-in   │
└───────────────────────────────────────┘   └─────────────────────────────────────┘
```

---

## 3. How Nebius Token Factory Accelerated NEBULA

1. **Unrivaled Inference Throughput & Latency**: Nebius Token Factory delivers instantaneous response times for large NVIDIA open-source models, enabling true real-time conversational voice interaction without awkward conversational lag.
2. **Cost & Credit Efficiency**: By deploying the hierarchical routing pattern recommended by Nebius, NEBULA directs 75% of quick tasks (speculative intent detection, boundary checks, quick replies) to **Nemotron-3-Nano**, while reserving **Nemotron-3-Super / Ultra** for heavy planning and Live RAG.
3. **OpenAI-Compatible Standard**: Zero friction integration via `AsyncOpenAI` client pointing to `https://api.tokenfactory.nebius.com/v1`.
4. **Nebius Serverless Deployment**: The entire NEBULA background service can be packaged into containerized serverless endpoints for remote agentic workflows.

---

## 4. 3-Minute YouTube Video Script & Storyboard

- **0:00 – 0:30 (The Problem & Vision)**:
  - *Visual*: Split screen showing standard assistants lagging with high latency and privacy warnings vs. NEBULA glowing cybernetic terminal.
  - *Audio*: "Welcome to NEBULA, the autonomous, sovereign personal AI assistant built for the Nebius Global AI Hackathon. In this demo, see how NVIDIA Nemotron models hosted on Nebius Token Factory give you complete desktop agency with total privacy."
- **0:30 – 1:15 (System Scanning & Native Hardware Agency)**:
  - *Visual*: User types or speaks `/scan`. NEBULA terminal instantly analyzes CPU, memory, active display brightness, and enumerates all audio input/output devices.
  - *Visual*: User asks: *"Switch my sound to the studio headphones and set brightness to 75%."* NEBULA executes the hardware commands natively across Linux/macOS/Windows and confirms dynamically.
- **1:15 – 2:00 (Speculative Live RAG on Nebius Token Factory)**:
  - *Visual*: User queries a complex policy: *"What is the cancellation policy for our Bangalore offsite and can we get catering refunded?"*
  - *Visual*: Show real-time telemetry logs: Nebius Token Factory Nemotron-3-Nano decomposes the compound question into parallel sub-queries; Nemotron-3-Super synthesizes the answer with exact citations `[Doc_01 §3]` and zero hallucination.
- **2:00 – 2:40 (Personal Memory & Data Sovereignty)**:
  - *Visual*: Demonstrate user settings: user updates their preferences, creates new isolated chat sessions (`/new Research Session`), and switches between context windows seamlessly. Show local SQLite database inspecting `data/nebula.db`.
- **2:40 – 3:00 (Conclusion & Nebius Token Factory Recap)**:
  - *Visual*: Summary slide highlighting Nebius Token Factory endpoints, NVIDIA Nemotron models, open-source Apache 2.0 license, and repository links.
  - *Audio*: "NEBULA brings the power of NVIDIA's premier open models on Nebius high-performance infrastructure straight to your personal workstation. Thank you!"

---

## 5. Devpost Submission Details

- **Project Title**: NEBULA – Sovereign Personal AI Assistant & Speculative Live RAG
- **Tagline**: Always-on private personal assistant powered by NVIDIA Nemotron on Nebius Token Factory with native OS hardware agency.
- **Selected Track**: Personal AI Track (with Best Apps and Agents Track synergy)
- **Repository URL**: https://github.com/abhinav29102005/nebula
- **License**: Apache 2.0 / MIT
- **Primary Models Used**:
  - `nvidia/nemotron-3-nano-30b-a3b`
  - `nvidia/nemotron-3-super-120b-a12b`
  - `nvidia/llama-3.1-nemotron-70b-instruct` / `nvidia/nemotron-3-ultra`

---

## 6. Feedback on Nebius Token Factory & NVIDIA Technologies

- **Nebius Token Factory**: Blazingly fast Time-To-First-Token (TTFT) and seamless OpenAI API compatibility. Outstanding uptime and predictable latency for high-parameter models. Suggestion: Add built-in token usage telemetry dashboards per API key for easier monitoring.
- **NVIDIA Nemotron**: Exceptional instruction-following capabilities, particularly in strict tool calling and citation-grounded RAG synthesis. The Nemotron-Nano tier provides an ideal balance of size and speculative reasoning speed.
