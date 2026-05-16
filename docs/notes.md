
# Journal

---

## 2026-05-16 — Project Scope Defined

**Author:** Diego + Valdrin

### What we decided

We decided to build a streaming analytics system for the **DEBS 2013 Grand Challenge Soccer Monitoring dataset**.

The project will use **Apache Spark Structured Streaming** to process timestamped soccer sensor data as a simulated live stream. Since the original dataset is stored as files, we will reconstruct a stream by replaying the data in chronological order.

### Selected project focus

The project will focus on a feasible subset of the original DEBS challenge:

1. **Running analysis**
   - classify player movement intensity,
   - compute speed-based statistics,
   - compute player activity over time.

2. **Heat map analysis**
   - divide the field into grid cells,
   - compute player/team spatial distribution,
   - visualize field occupation.

3. **Optional simplified ball possession**
   - identify the ball sensor,
   - find the closest player to the ball,
   - estimate team possession with a simplified proxy.

### Reasoning

This scope is realistic for a two-person team because:

- the dataset is predefined,
- the data is already timestamped,
- Spark Structured Streaming is appropriate for incremental processing,
- running analysis and heat maps are easier to explain visually,
- the live demo can be made reliable with a subset of the match.

### Current status

Status: **Done**

---

## 2026-05-15 — Repository Structure Started

**Author:** Valdrin

### What we prepared

The repository currently contains the basic project files and folders.

Important files:

```text
src/
├── clean_data.py
└── config.py

```
## 2026-05-16 — Current Repository Structure

Author: Diego

### Current structure

The repository is now organized with folders for source code, raw data, processed data, stream simulation, output, checkpoints, and documentation.

```text
SOCCER-ANALYTICS/
│
├── src/
│   ├── clean_data.py
│   └── config.py
│
├── data/
│   ├── raw/
│   ├── metadata/
│   ├── processed/
│   ├── stream_input/
│   └── output/
│
├── presentation/
|
├── reportContent/
|
├── checkpoints/
│
├── docs/
│   ├── figures/
│   └── notes.md
│
├── main.py
├── README.md
├── requirements.txt
└── .gitignore