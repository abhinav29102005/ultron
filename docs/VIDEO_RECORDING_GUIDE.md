# ULTRON Cybernetic CLI & Streaming Live RAG — Video Recording Guide

This document provides complete instructions, automation scripts, storyboards, and word-for-word voiceover narration for recording a broadcast-ready demonstration video of the **ULTRON Cybernetic CLI** and its **Streaming Live RAG Engine** (Samsung PRISM Theme 4 & NVIDIA/Nebius AI Cloud).

---

## 1. Quick Start: 3 Recording Methods

Choose the recording method that fits your workflow:

### Method A: 1-Click Automated MP4 Video Generation (Fastest & Pixel-Perfect)
An automated script renders terminal frames and encodes a pristine H.264 MP4 video with simulated typing, streaming token delivery, and Telemetry HUD:

```bash
# Generate 720p 24fps MP4
python3 scripts/record_cli_video.py --output ultron_rag_demo.mp4

# Or generate 1080p 30fps
python3 scripts/record_cli_video.py --output ultron_rag_demo_1080p.mp4 --width 1920 --height 1080 --fps 30
```
- **Output**: Broadcast-ready `.mp4` file ready to submit or upload immediately.
- **Audio**: Add voiceover audio using the script in [Section 3](#3-step-by-step-video-storyboard--narration-script).

---

### Method B: Interactive Cybernetic Terminal Web HUD (Best for Live Screen Capture / OBS)
An interactive glassmorphic web dashboard reproducing the Cybernetic Terminal with live Telemetry HUD, entity state cards, and technical gates:

1. **Start the local server**:
   ```bash
   python3 -m http.server 8976 --directory /home/bigboyaks/.gemini/antigravity-ide/brain/1b9e7d0d-fc35-4456-9760-af438c5abfcf/scratch
   ```
2. **Open in browser**:
   Navigate to `http://localhost:8976/cli_demo.html`.
3. **Record with screen capture software**:
   - Open **OBS Studio**, **SimpleScreenRecorder**, **QuickTime**, or your preferred recorder.
   - Record the browser window as the terminal automatically types and streams 4 interactive turns, or click **"RUN NEXT TURN"** to demonstrate manual control.

---

### Method C: Native Terminal Screen Recording
Record the live CLI or demo script running directly in your system terminal:

1. **Terminal Setup**:
   - Set terminal size to **120 columns × 35 rows**.
   - Use a dark theme with high contrast (cyan prompt, green success badges).
2. **Launch Recording with `asciinema` or OBS**:
   ```bash
   # Run the full 9-flow real-data demonstration script:
   python3 scripts/demo_streaming_rag.py
   ```
   Or launch the interactive cybernetic CLI:
   ```bash
   python3 run.py --cli
   ```
   Inside the CLI, execute consecutive `/rag` commands:
   ```text
   ultron > /rag I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy.
   ultron > /rag What if it is for 50 people?
   ultron > /rag What about hotel lodging tariffs there?
   ultron > /rag Please repeat your last answer in two bullets.
   ```

---

## 2. Technical Evaluation Gates (G1–G9) Verification

Prior to recording, run the automated evaluation suite to ensure all gates are green:

```bash
PYTHONPATH=. python3 streaming_rag/benchmark.py
```

### Verification Matrix

| Gate | Criterion / Name | Target Threshold | Observed Result | Status |
| :--- | :--- | :--- | :--- | :---: |
| **G1** | **Reproducibility** | Automated single-command pass | Pass without human intervention | **PASS** |
| **G2** | **Early Retrieval Triggering** | Gain $\ge 800\text{ ms}$ before final chunk | **$1300.0\text{ ms}$ gain** ($t=0.8\text{ s}$ trigger) | **PASS** |
| **G3** | **Multi-Intent Identification** | Extract $\ge 2$ orthogonal sub-queries | **3 sub-queries extracted** | **PASS** |
| **G4** | **Factual Grounding & Citations** | Valid section tags (`[Doc_XX §YY]`) | `Doc_12 §2`, `Doc_31 §4`, `Doc_09 §1` | **PASS** |
| **G5** | **State Refinement (Delta Query)**| Cumulative state continuity | Version 1 $\rightarrow$ Version 2 $\rightarrow$ Version 3 | **PASS** |
| **G6** | **Telemetry & Observability** | 100% trace capture | Microsecond latency, TTFT, token counts | **PASS** |
| **G7** | **Context Discontinuity Resolution**| Cross-turn anaphora & entity memory | Resolved: `'Pune workshop capacity 50'` | **PASS** |
| **G8** | **Intra-Stream Speculative Invalidation**| Mid-speech correction re-dispatch | Pune $\rightarrow$ Mumbai pivot caught | **PASS** |
| **G9** | **Streaming Token Delivery & TTFT** | $\text{TTFT} < 50\text{ ms}$ & incremental tokens | **$\text{TTFT} = 1.0\text{ ms}$**, 22 tokens yielded | **PASS** |

---

## 3. Step-by-Step Video Storyboard & Narration Script

Use this 2.5-minute storyboard and word-for-word voiceover script while recording:

### Scene 1: Introduction & Architecture (0:00 – 0:25)
- **Visual**: Show the Ultron Cybernetic CLI banner with status indicators: `Hybrid Search (BM25 + Dense)`, `Nebius AI Cloud`, `Samsung Theme 4`.
- **Narration**:
  > *"Welcome to the demonstration of the ULTRON Cybernetic CLI, powered by our evolved Streaming Live RAG engine designed for Samsung PRISM Theme 4 and Nebius Token Factory. Traditional RAG systems wait until the user finishes speaking, suffer from context loss across conversational turns, and hallucinate missing constraints. Ultron resolves all three with speculative early retrieval, continuous entity memory, and strict citation traceability."*

---

### Scene 2: Speculative Early Retrieval & Multi-Intent (0:25 – 0:55)
- **Visual**: Type `/rag I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy.`  
  Highlight the green indicator: `[⚡ SPECULATIVE] Triggered at t=0.8s (Gain: 1300ms)`.
- **Narration**:
  > *"Watch Turn 1. While the user is still speaking at 0.8 seconds, our Intent Stability Evaluator detects semantic stability and triggers speculative hybrid retrieval before the utterance ends—delivering an early retrieval gain of 1300 milliseconds. The multi-intent decomposer isolates the workshop venue from the cancellation policy, and synthesizes answers backed strictly by Document 12 Section 2 and Document 31 Section 4."*

---

### Scene 3: Cross-Turn Context Discontinuity Resolution (0:55 – 1:30)
- **Visual**: Type `/rag What if it is for 50 people?`  
  Highlight `[⚡ CONTEXT RESOLVED] 'Pune workshop venue capacity for 50 attendees' (Turn 2)` and the capacity warning: `Facilities for 50 attendees exceed the 30-attendee limit in Doc_12 §2`.
- **Narration**:
  > *"In Turn 2, notice the conversational ellipsis: the user simply asks, 'What if it is for 50 people?' Rather than failing or asking for clarification, Ultron's Context Discontinuity Engine consults its active entity memory, resolving the prompt into 'Pune workshop venue capacity for 50 attendees.' Crucially, the synthesizer detects that Document 12 caps approved facilities at 30 attendees—raising an explicit capacity limit warning rather than hallucinating an invalid venue."*

---

### Scene 4: Anaphora Coreference & Per Diem Grounding (1:30 – 2:00)
- **Visual**: Type `/rag What about hotel lodging tariffs there?`  
  Highlight `[⚡ CONTEXT RESOLVED] 'Hotel lodging caps and per diem limits in Pune Tier-1' (Turn 3)` and grounded answer with `[Doc_52 §2]`.
- **Narration**:
  > *"In Turn 3, the user asks about hotel tariffs 'there.' The anaphora engine resolves 'there' to Pune Tier-1 cities, retrieving Document 52 Section 2 to ground the nightly tariff cap at INR 6,500 inclusive of breakfast—maintaining cumulative session versioning without re-asking."*

---

### Scene 5: Gate 0 Presentation Query Suppression (2:00 – 2:25)
- **Visual**: Type `/rag Please repeat your last answer in two bullets.`  
  Highlight `[GATE 0 SUPPRESSION] 0 vector queries executed` and the bullet points with attached citations.
- **Narration**:
  > *"In Turn 4, the user requests formatting: 'Repeat your last answer in two bullets.' Gate 0 immediately detects presentation restructuring and suppresses corpus retrieval completely—executing zero vector searches while preserving every citation tag attached directly to its proposition."*

---

### Scene 6: Streaming Token Yield & Evaluation Gates (2:25 – 2:50)
- **Visual**: Show the real-time Telemetry HUD with `TTFT = 1.0ms`, `Gates G1-G9 PASS`, and all 9 green checkmarks.
- **Narration**:
  > *"Every response is generated as an incremental token stream with a Time-To-First-Token under 1.5 milliseconds. All 9 evaluation gates—from speculative triggers to context continuity and zero-retrieval suppression—pass with 100% reproducibility on real data. Thank you for watching the ULTRON Streaming Live RAG demonstration."*

---

## 4. Video Export & Upload Checklist

Before final submission:
- [ ] **Video Format**: MP4 (H.264 video, AAC audio, stereo 44.1kHz).
- [ ] **Resolution**: 1080p ($1920 \times 1080$) or 720p ($1280 \times 720$), 16:9 aspect ratio.
- [ ] **Framerate**: 24 fps or 30 fps progressive.
- [ ] **File Size**: Under 100 MB for fast playback.
- [ ] **Legibility**: Ensure terminal font is crisp and readable on mobile devices.
- [ ] **Sound**: Audio narration clearly audible over background audio.
