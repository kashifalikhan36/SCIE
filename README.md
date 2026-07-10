# SCIE: Smart Candidate Identification Engine

Welcome to **SCIE**, an intelligent pipeline designed to automatically evaluate and identify the target "Candidate" within an interview session using an Evidence Fusion Architecture and Large Language Models (LLMs). 

This project simulates a real-world analytics environment where video, audio, and participant metadata are processed to confidently determine who the candidate is among the participants, dynamically handling missing data without arbitrary penalties.

---

## Demo

[Insert YouTube Video Demo Here]

---

## Architecture

The SCIE system operates in two distinct phases: **Data Generation** (processing raw video into structured intelligence) and **Candidate Detection** (analyzing that intelligence using a dynamic, weighted Fusion Engine).

```mermaid
graph TD
    %% Phase 1: Data Generation
    subgraph Data Generation Phase
        A[Raw Interview Video] -->|Extract Audio| B(dummy_data_generator.py)
        B -->|Audio via Groq Whisper| C[Raw Text Transcript]
        C -->|Azure OpenAI Reasoning| D[Structured Mock data.json]
        D -->|prune_json.py| E[Strictly Validated data.json]
    end

    %% Phase 2: Candidate Detection
    subgraph Candidate Detection System
        E --> F(detector.py Orchestrator)
        F --> G1(Identity Correlation)
        F --> G2(Name Match)
        F --> G3(Conversation Role)
        F --> G4(Transcript Mentions)
        F --> G5(Speaking Behaviour)
        F --> G6(Event Timeline)
        F --> G7(Webcam Behaviour)
        F --> G8(Screen Share)
        F --> G9(Interviewer Detection)
        
        G1 --> H(fusion_engine.py)
        G2 --> H
        G3 --> H
        G4 --> H
        G5 --> H
        G6 --> H
        G7 --> H
        G8 --> H
        G9 --> H
        
        H -->|Dynamic Normalization| I{Ambiguity Check?}
        I -->|Score Diff > 5| J[Explainable Output Generated]
        I -->|Score Diff < 5| K[Marked as AMBIGUOUS]
    end
```

---

## Approach

The core philosophy of SCIE is **Evidence Fusion**. Instead of relying on a single point of failure (e.g., face recognition or simple email matching), every available signal contributes evidence towards the final decision. Every module asks: *"Does this piece of evidence increase or decrease the probability that this participant is the candidate?"* If data is missing (like an email address), the module gracefully skips rather than crashing or arbitrarily penalizing the participant.

### The Evidence Modules

1. **Conversation Role (`conversation_role.py`) - Weight: 25**
   - *Approach*: Feeds the transcript to **Azure OpenAI (`gpt-5.3-chat`)** to identify structured conversational dynamics: who asks questions, who answers, who introduces themselves, and who is evaluated.

2. **Transcript Mentions (`transcript_mentions.py`) - Weight: 15**
   - *Approach*: Uses an LLM to scan the transcript to see if a participant is repeatedly addressed by the known candidate's name.

3. **Speaking Behaviour (`speaking.py`) - Weight: 15**
   - *Approach*: Calculates total speaking duration, speaking ratio, number of turns, and average answer length to identify candidates responding to questions.

4. **Name Match (`name_match.py`) - Weight: 15**
   - *Approach*: Uses **RapidFuzz** for robust string matching, gracefully handling exact matches, partial names, typos, and initials against the calendar metadata.

5. **Identity Correlation (`identity_correlation.py`) - Weight: 15 (Dynamic)**
   - *Approach*: Compares participant emails or account IDs to the calendar invite. If identity information does not exist, the module skips completely.

6. **Event Timeline (`timeline.py`) - Weight: 5**
   - *Approach*: Merges all events (Join, Webcam, Speaking, Screen Share) chronologically to evaluate if a participant's timeline resembles a typical candidate sequence.

7. **Webcam Behaviour (`webcam.py`) - Weight: 5**
   - *Approach*: Evaluates camera uptime, stability, continuity, and toggles.

8. **Screen Share (`screen_share.py`) - Weight: 3**
   - *Approach*: Offers a minor confidence boost if a participant shares their screen. Never penalizes participants if no one shares.

9. **Interviewer Detection (`interviewer_detection.py`) - Penalty Module**
   - *Approach*: Heavily penalizes participants whose display names match known interviewers in the calendar metadata.

### The Dynamic Fusion Engine

The `FusionEngine` aggregates scores based on their assigned weights. 

**Dynamic Normalization**: 
If a module is skipped (e.g., no email available), its weight is excluded from the total normalization pool. This ensures that the final confidence score remains an accurate 0-100% metric based *only* on the available evidence.

**Explainability Engine**: 
The final output automatically generates an explanation detailing exactly *why* a participant was selected. Example output:
```
[+] Exact display name match: Chivukula Jagannath
[+] Participant shared screen 1 time(s).
[+] Speaking ratio 49.1% and average answer length (70.8s) strongly suggest candidate responding to questions.
```

**Ambiguity Handling:**
If the final scores of the top two participants are within 5 points of each other, the engine refuses to force a winner. It flags the decision as `AMBIGUOUS`, returning suggestions and highlighting the missing evidence modules.

---

## Trade-offs

During the design and implementation of SCIE, several engineering trade-offs were made:

1. **LLM vs. Heuristics for Transcript Analysis**: We opted to use Azure OpenAI for deep conversational semantic analysis rather than simple regex heuristics. *Trade-off*: Higher accuracy and adaptability at the cost of API latency and token costs.
2. **Missing Data Handling vs. Hard Requirements**: We chose a dynamic weighting system that skips missing data. *Trade-off*: Highly resilient to imperfect data streams, but risks false positives if too many high-weight modules are skipped due to missing data.
3. **Evidence Fusion vs. Biometrics**: We completely avoided facial recognition and voice biometrics. *Trade-off*: Eliminates heavy privacy/compliance hurdles and complex media processing pipelines, but trades away the deterministic certainty of biometric matching.

---

## What You'd Improve Next

If given more time and resources, the next iterations of SCIE would focus on:

1. **Vector Embeddings for Conversational Nuance**: Rather than sending entire transcripts to the LLM, we could compute embeddings for speaking turns to identify semantic clusters representing "Interviewing Questions" vs "Technical Answers."
2. **Real-time Streaming Support**: Refactor the architecture to process events as they stream via WebSockets rather than waiting for post-call batch processing.
3. **Advanced Timeline Interleaving**: Build deeper heuristics into `timeline.py` to recognize specific interactive patterns, such as "Interviewer speaks -> 2 seconds latency -> Candidate speaks for 3 minutes -> Screen share begins."
4. **Multi-Candidate Evaluation**: Extend the logic to gracefully handle group interviews (e.g., panel interviews with multiple candidates).

---

## Tech Stack & Tools Used
- **Python 3.12+**: Core language using modular OOP architecture.
- **Pydantic**: Guarantees strict data validation and injects explainable `metadata` tags.
- **RapidFuzz**: Deterministic high-performance string matching.
- **Groq Whisper**: Audio transcription pipeline.
- **Azure OpenAI**: LLM semantic parsing and conversational logic reasoning.