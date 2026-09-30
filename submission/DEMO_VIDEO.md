# Samsung PRISM GenAI Hackathon 2026 — Theme 4: Streaming Live RAG
## Demonstration Video & Walkthrough Guide (Under 5 Minutes)

**Team Name**: 4 Bottle Codeka  
**College**: Thapar Institute of Engineering & Technology, Patiala  
**Members**: Abhinav Kumar Singh, Sukhansh Mittal, Lakkshya Jha, Vikramaditya Singh  
**Demo Video Link**: [Insert Final Recorded Video Link: YouTube / Google Drive]  

---

### Demonstration Video Structure (9 Scenes)

| Scene | Duration | Title | Key Phenomenon Demonstrated |
|:---:|:---:|:---|:---|
| **1** | 0:00 – 0:35 | **Technical Evaluation Gates (G1–G9)** | Automated execution of all 10 gates showing 100% green pass with TTFT, latency, and citation metrics. |
| **2** | 0:35 – 1:05 | **Speculative Early Retrieval** | Streaming speech triggers hybrid search at token 7 ($t=0.8\text{s}$), achieving +1,300ms time gain before completion. |
| **3** | 1:05 – 1:40 | **Compound Multi-Intent Decomposition** | Complex multi-topic utterance split into 3 orthogonal sub-queries and retrieved in parallel. |
| **4** | 1:40 – 2:15 | **Context Discontinuity & Anaphora** | Resolves pronouns (*"it"*) and deictic markers (*"there"*, *"for 50 people"*) across multi-turn dialog. |
| **5** | 2:15 – 2:50 | **Intra-Stream Speculative Pivot** | Mid-sentence user self-correction (*"Pune... actually Mumbai"*) dynamically purges stale cache and re-dispatches query. |
| **6** | 2:50 – 3:30 | **Session Refinement ($V_1 \to V_2$)** | Incremental constraint update mutates existing state without clearing prior conversational baseline. |
| **7** | 3:30 – 4:00 | **Gate 0 Presentation Query Suppression** | Formatting request (*"format into two bullets"*) executes 0 vector searches while preserving citations intact. |
| **8** | 4:00 – 4:30 | **Negative Control & Zero Hallucination** | Out-of-corpus query triggers explicit uncertainty with 0 fabricated document IDs or hallucinated policies. |
| **9** | 4:30 – 5:00 | **Real-Time Telemetry HUD & Wrap-up** | Live terminal HUD displaying turn latency, TTFT, token budgets, and exact section citations. |

---

### How Evaluators Can Reproduce the Demonstration
Evaluators can replay the exact demonstration shown in the video:
```bash
# Interactive Step-by-Step Mode (press ENTER between scenes)
python3 run.py --cli
# Then type: /demo

# Or run directly from terminal
python3 run.py demo

# Automated fast replay
python3 run.py demo --auto --fast
```
