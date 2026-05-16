# Soccer Analytics

**Real-Time Soccer Monitoring with Apache Spark Structured Streaming**

Course: **Distributed Information Systems Spring 2026**  
Project type: **Workshop Project**  
Team: **Valdrin Shremetaj**, **Diego Gonçalves Simao**  
University: **University of Basel**  

---

## 1. Project Overview

This project implements a real-time soccer monitoring system using **Apache Spark Structured Streaming**.

The project is based on the **DEBS 2013 Grand Challenge: Soccer Monitoring** dataset. The dataset contains high-frequency position events from wireless sensors placed in the players' shoes, in the ball, and for the goalkeeper also in the hands.

Since the original data is stored as timestamped files, we reconstruct a stream by replaying the data in chronological order. Apache Spark then processes the incoming data incrementally and computes live match statistics.

The main focus of the project is to implement a manageable subset of the DEBS 2013 queries:

1. running analysis,
2. heat map generation,
3. optional simplified ball possession.

The goal is to build a working and demonstrable streaming analytics system, not to fully reproduce the entire DEBS competition solution.

---

## 2. Project Goal

The goal of this project is to demonstrate how Apache Spark Structured Streaming can be used for real-time analytics over high-frequency sports sensor data.

The system should:

1. load raw DEBS soccer sensor data,
2. load metadata mapping sensors to players and teams,
3. clean and normalize the raw sensor records,
4. reconstruct a live stream from the timestamped data,
5. process the stream with Apache Spark Structured Streaming,
6. compute real-time soccer analytics,
7. write continuously updated result streams,
8. visualize the results during a live demo.

The project should go beyond simple counting by extracting interpretable match statistics such as player running intensity, distance covered, spatial occupation of the field, and possibly approximate ball possession.

---

## 3. Dataset

### 3.1 Dataset Name

**DEBS 2013 Grand Challenge Soccer Monitoring Dataset**

### 3.2 Dataset Source

Dataset source:

```text
https://debs.org/grand-challenges/2013/
```

Raw sensor data:

```text
[Insert downloaded raw sensor file name here]
```

Metadata file:

```text
[Insert metadata file name here]
```

Optional referee/statistics file:

```text
[Insert referee events/statistics file name here]
```

---

## 4. Dataset Description

The dataset was collected during a soccer match using a real-time locating system. Each event describes the position, velocity, and acceleration of one sensor.

The raw sensor data contains the following schema:

```text
sid, ts, x, y, z, |v|, |a|, vx, vy, vz, ax, ay, az
```

### 4.1 Column Meaning

| Column | Meaning |
|---|---|
| `sid` | Sensor identifier |
| `ts` | Timestamp in picoseconds |
| `x` | X-coordinate in millimetres |
| `y` | Y-coordinate in millimetres |
| `z` | Z-coordinate in millimetres |
| `|v|` | Absolute velocity in micrometres per second |
| `|a|` | Absolute acceleration in micrometres per second squared |
| `vx` | X component of velocity direction |
| `vy` | Y component of velocity direction |
| `vz` | Z component of velocity direction |
| `ax` | X component of acceleration direction |
| `ay` | Y component of acceleration direction |
| `az` | Z component of acceleration direction |

### 4.2 Important Dataset Facts

| Property | Value |
|---|---|
| Player sensor frequency | 200 Hz |
| Ball sensor frequency | 2000 Hz |
| Approximate total event rate | 15,000 position events per second |
| Match format | Two halves of 30 minutes |
| Teams | 7 players per team |
| Coordinate origin | Center of the field |
| Coordinate unit | Millimetres |
| Timestamp unit | Picoseconds |

### 4.3 Game Time Information

The DEBS guide provides the following approximate game timestamps:

| Half | Start Timestamp | End Timestamp |
|---|---:|---:|
| 1st half | `10753295594424116` | `12557295594424116` |
| 2nd half | `13086639146403495` | `14879639146403495` |

The end of the first half contains technical issues where the active ball transmitter is missing for the last approximately 2.5 minutes. For this reason, ball possession and shot-related analysis may be unreliable in that interval.

---

## 5. Selected Project Scope

The original DEBS challenge defines four main queries:

1. running analysis,
2. ball possession,
3. heat map,
4. shot on goal.

For this workshop project, we focus on a realistic subset that is feasible for a two-person team.

### 5.1 Main Features

The planned main features are:

1. **Running Analysis**
   - classify player movement intensity,
   - compute time and distance per intensity level,
   - aggregate statistics over time windows.

2. **Heat Map**
   - divide the field into grid cells,
   - compute how much time each player spends in each region,
   - visualize player or team spatial distribution.

3. **Simplified Ball Possession**
   - estimate which player or team is closest to the ball,
   - optionally detect possession changes using distance and acceleration thresholds,
   - compare the result with the provided possession statistics if feasible.

### 5.2 Optional Features

Optional features if time allows:

- shot-on-goal approximation,
- anomaly detection,
- live field visualization,
- comparison against provided reference statistics,
- Docker-based local Spark cluster.

---

## 6. Running Intensity Definition

For the running analysis, player speed is classified into the intensity levels defined by the DEBS guide.

| Intensity | Speed Range |
|---|---:|
| Standing | 0-1 km/h |
| Trot | up to 11 km/h |
| Low speed run | up to 14 km/h |
| Medium speed run | up to 17 km/h |
| High speed run | up to 24 km/h |
| Sprint | faster than 24 km/h |

The raw velocity is given in micrometres per second. Therefore, we convert speed into metres per second and kilometres per hour during preprocessing.

Planned speed conversion:

```text
speed_m_per_s = abs_velocity_um_per_s * 1e-6
speed_km_per_h = speed_m_per_s * 3.6
```

If necessary, speed values will be smoothed to reduce noise.

---

## 7. Repository Structure

```text
SOCCER-ANALYTICS/
│
├── src/
│   ├── clean_data.py                  # Cleans and prepares raw sensor data
│   ├── config.py                      # Central paths and constants
│   ├── metadata_loader.py             # Loads sensor/player/team metadata
│   ├── replay_full_game.py            # Replays cleaned data as simulated stream
│   ├── streaming_job.py               # Main Spark Structured Streaming job
│   ├── running_analysis.py            # Running intensity logic
│   ├── heatmap_analysis.py            # Heat map logic
│   ├── possession_analysis.py         # Optional possession logic
│   ├── dashboard.py                   # Optional Streamlit dashboard
│   └── utils.py                       # Helper functions
│
├── data/
│   ├── raw/                           # Original downloaded DEBS files
│   ├── metadata/                      # Metadata files
│   ├── clean/                         # Cleaned and normalized data
│   ├── stream_input/                  # Simulated streaming input
│   └── output/                        # Spark result streams
│
├── checkpoints/                       # Spark checkpoint directories
│
├── docs/
│   ├── figures/                       # Figures for report and presentation
│   └── notes.md                       # Development notes
│
├── presentation/
│   └── [presentation-file]            # Final workshop presentation
│
├── reportContent/
│   └── [latex-report-files]           # LaTeX report files
│
├── main.py                            # Main entry point
├── requirements.txt                   # Python dependencies
├── README.md                          # Project documentation
├── .gitignore
└── LICENSE                            # Optional
```

---

## 8. Requirements

Recommended environment:

```text
Python: 3.10 or newer
Java: 17 recommended
Spark: Installed through PySpark
Operating system: Windows / macOS / Linux
```

Spark 3.5 should be used with Java 17 for the safest setup.

---

## 9. Installation

### 9.1 Clone the Repository

```bash
git clone [repository-url]
cd SOCCER-ANALYTICS
```

### 9.2 Create a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 9.3 Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 9.4 Check Java

```bash
java -version
```

Expected output:

```text
openjdk version "17.x.x"
```

### 9.5 Check PySpark

```bash
python -c "from pyspark.sql import SparkSession; spark = SparkSession.builder.appName('test').getOrCreate(); print(spark.range(5).collect()); spark.stop()"
```

Expected output:

```text
[Row(id=0), Row(id=1), Row(id=2), Row(id=3), Row(id=4)]
```

---

## 10. Configuration

Configuration values are stored in:

```text
src/config.py
```

Example configuration:

```python
RAW_DATA_DIR = "data/raw"
METADATA_DIR = "data/metadata"
CLEAN_DATA_DIR = "data/clean"
STREAM_INPUT_DIR = "data/stream_input"
OUTPUT_DIR = "data/output"
CHECKPOINT_DIR = "checkpoints"

RAW_SENSOR_FILE = "data/raw/[raw-sensor-file]"
METADATA_FILE = "data/metadata/[metadata-file]"

REPLAY_BATCH_SIZE = 50000
REPLAY_SLEEP_SECONDS = 1

WINDOW_DURATION_SHORT = "1 minute"
WINDOW_DURATION_MEDIUM = "5 minutes"
WINDOW_DURATION_LONG = "20 minutes"

WATERMARK_DURATION = "30 seconds"

FIELD_X_MIN = 0
FIELD_X_MAX = 52483
FIELD_Y_MIN = -33960
FIELD_Y_MAX = 33965
```

The field coordinates can be adjusted after inspecting the metadata file.

---

## 11. Pipeline Overview

```text
Raw DEBS Sensor Data
        ↓
Metadata Loading
        ↓
Data Cleaning and Normalization
        ↓
Stream Replay
        ↓
Spark Structured Streaming
        ↓
Running Analysis / Heat Map / Possession Proxy
        ↓
Output Files
        ↓
Dashboard and Live Demo
```

---

## 12. Step 1: Data Cleaning

The cleaning script reads the raw DEBS sensor data and converts it into a Spark-friendly format.

Input:

```text
data/raw/
data/metadata/
```

Output:

```text
data/clean/
```

Run:

```bash
python src/clean_data.py
```

Expected output:

```text
data/clean/clean_sensor_data.parquet
```

or:

```text
data/clean/clean_sensor_data.csv
```

Cleaning tasks:

- [ ] Load raw sensor file
- [ ] Apply correct schema
- [ ] Convert timestamp from picoseconds to seconds or milliseconds
- [ ] Convert Spark event time to timestamp format
- [ ] Convert coordinates from millimetres to metres if useful
- [ ] Convert speed from micrometres per second to km/h
- [ ] Convert acceleration from micrometres per second squared to m/s²
- [ ] Load metadata
- [ ] Map sensor IDs to player IDs
- [ ] Map player IDs to team IDs
- [ ] Identify ball sensor ID
- [ ] Remove invalid or incomplete rows
- [ ] Save cleaned data

---

## 13. Step 2: Metadata Loading

The metadata file is needed to connect raw sensor IDs with players, teams, and the ball.

Planned metadata output:

| Column | Description |
|---|---|
| `sid` | Sensor ID |
| `player_id` | Player ID |
| `team_id` | Team ID |
| `object_type` | Player, ball, goalkeeper hand, unknown |
| `sensor_position` | Left foot, right foot, hand, ball |

Run:

```bash
python src/metadata_loader.py
```

Expected output:

```text
data/clean/sensor_metadata.csv
```

Tasks:

- [ ] Load original metadata file
- [ ] Extract player/team mapping
- [ ] Extract sensor/player mapping
- [ ] Identify ball sensor
- [ ] Save normalized metadata table

---

## 14. Step 3: Stream Replay

The replay script simulates a live stream by gradually writing small batches of cleaned records into the streaming input folder.

Input:

```text
data/clean/clean_sensor_data.parquet
```

Output:

```text
data/stream_input/
```

Run:

```bash
python src/replay_full_game.py
```

The script should create files such as:

```text
data/stream_input/batch_000001.parquet
data/stream_input/batch_000002.parquet
data/stream_input/batch_000003.parquet
```

Planned replay behavior:

- [ ] Read cleaned data
- [ ] Sort by original timestamp
- [ ] Split into batches
- [ ] Write one batch every few seconds
- [ ] Print replay progress
- [ ] Support demo mode with faster replay
- [ ] Support first-half-only mode
- [ ] Support small test subset mode

Important: the replay does not need to wait according to the original timestamp distance. The stream can be replayed faster for the demo, but all analytics must still use the event timestamps from the data.

---

## 15. Step 4: Spark Structured Streaming Job

Spark reads continuously from:

```text
data/stream_input/
```

and writes result streams to:

```text
data/output/
```

Run:

```bash
python main.py
```

or:

```bash
python src/streaming_job.py
```

Spark processing tasks:

- [ ] Define schema manually
- [ ] Read stream from file source
- [ ] Use event-time column
- [ ] Apply watermarking
- [ ] Join with metadata
- [ ] Compute running analysis
- [ ] Compute heat map
- [ ] Optionally compute possession proxy
- [ ] Write each result stream separately
- [ ] Store checkpoints

Possible output folders:

```text
data/output/running_current/
data/output/running_aggregate/
data/output/heatmap/
data/output/possession/
```

---

## 16. Analytics 1: Running Analysis

### Goal

Calculate running performance statistics for each active player.

### Intensity Classes

| Intensity | Speed |
|---|---:|
| Standing | 0-1 km/h |
| Trot | 1-11 km/h |
| Low speed run | 11-14 km/h |
| Medium speed run | 14-17 km/h |
| High speed run | 17-24 km/h |
| Sprint | >24 km/h |

### Planned Output: Current Running Statistics

```text
ts_start, ts_stop, player_id, intensity, distance, speed
```

### Planned Output: Aggregate Running Statistics

```text
ts,
player_id,
standing_time,
standing_distance,
trot_time,
trot_distance,
low_time,
low_distance,
medium_time,
medium_distance,
high_time,
high_distance,
sprint_time,
sprint_distance
```

### Planned Windows

```text
1 minute
5 minutes
20 minutes
whole game
```

### Simplification for Workshop

The original DEBS query requires very high update rates. For this project, we will compute the same type of statistics but use a lower output frequency suitable for a stable live demo.

Status: **[Not started / In progress / Done]**

---

## 17. Analytics 2: Heat Map

### Goal

Compute how much time each player spends in different regions of the field.

### Planned Grid Sizes

We will start with one grid size:

```text
8 x 13 = 104 cells
```

Optional additional grid sizes:

```text
16 x 25 = 400 cells
32 x 50 = 1600 cells
64 x 100 = 6400 cells
```

### Planned Output

```text
ts,
player_id,
cell_x1,
cell_y1,
cell_x2,
cell_y2,
percent_time_in_cell
```

### Planned Windows

```text
1 minute
5 minutes
10 minutes
whole game
```

### Simplification for Workshop

The first implementation will use the 8 x 13 grid. Higher-resolution grids can be added if performance and time allow.

Status: **[Not started / In progress / Done]**

---

## 18. Analytics 3: Simplified Ball Possession

### Goal

Estimate which player or team is in possession of the ball.

### Original DEBS Idea

A player obtains the ball when:

1. the ball is close to a player's foot,
2. the ball acceleration indicates a hit.

The DEBS guide uses:

```text
distance < 1 metre
ball acceleration >= 55 m/s²
```

### Planned Simplified Approach

We will implement a simplified possession proxy:

1. identify the ball sensor,
2. identify player foot sensors,
3. compute distance between ball and players,
4. assign ball proximity to the closest player within 1 metre,
5. aggregate possession proxy by player and team.

If time allows, we add the acceleration threshold to detect actual hits.

### Planned Player Output

```text
ts, player_id, possession_time, hits
```

### Planned Team Output

```text
ts, team_id, possession_time, possession_percent
```

Status: **[Optional / Not started / In progress / Done]**

---

## 19. Optional Analytics: Shot on Goal

Shot-on-goal detection is part of the original DEBS challenge, but it is more complex than the other queries. It requires ball trajectory projection and goal-area intersection.

For this project, shot detection is considered optional and will only be implemented if the core pipeline is finished early.

Status: **[Optional]**

---

## 20. Visualization

The visualization will be implemented using:

```text
Streamlit
Plotly
Matplotlib
```

Run dashboard:

```bash
streamlit run src/dashboard.py
```

Planned dashboard views:

- [ ] current player running intensity
- [ ] aggregate distance per player
- [ ] time spent per intensity
- [ ] heat map by player
- [ ] heat map by team
- [ ] optional possession percentage
- [ ] current replay progress

---

## 21. Live Demo Plan

The presentation includes a live demo.

### Demo Goal

Show that Spark processes the DEBS soccer data incrementally as a stream and continuously updates match analytics.

### Demo Strategy

The live demo should be reliable and not too complex. Therefore, the demo will use:

```text
first-half subset or smaller selected data segment
```

instead of the full 2.6 GB raw file, unless performance is stable.

### Demo Steps

1. Clean old streaming folders.

Windows PowerShell:

```powershell
Remove-Item data/stream_input/* -Recurse -Force
Remove-Item data/output/* -Recurse -Force
Remove-Item checkpoints/* -Recurse -Force
```

macOS / Linux:

```bash
rm -rf data/stream_input/*
rm -rf data/output/*
rm -rf checkpoints/*
```

2. Start the Spark streaming job.

```bash
python main.py
```

3. Start the replay script in a second terminal.

```bash
python src/replay_full_game.py --demo
```

4. Open the dashboard.

```bash
streamlit run src/dashboard.py
```

5. Show live updates:
   - new batches appear in `data/stream_input/`,
   - Spark writes result streams to `data/output/`,
   - dashboard updates running statistics and heat map.

6. Explain one concrete example:
   - one player changes from trot to sprint,
   - aggregate distance updates,
   - heat map cell percentages change.

### Demo Fallback

If the live demo fails, use:

- precomputed output files,
- screenshots,
- a short recorded video,
- static plots generated from the same Spark output.

Fallback files:

```text
docs/figures/demo_running_analysis.png
docs/figures/demo_heatmap.png
docs/figures/demo_dashboard.png
```

---

## 22. Presentation Structure

Expected duration: **20 minutes including demo and Q&A**

| Part | Duration | Content |
|---|---:|---|
| Introduction | 2 min | Motivation and project goal |
| Dataset | 3 min | DEBS sensor data, schema, metadata |
| Architecture | 3 min | Cleaning, replay, Spark streaming, output |
| Implementation | 4 min | Running analysis and heat map logic |
| Results | 3 min | Main findings and visualizations |
| Live Demo | 4 min | Streaming pipeline in action |
| Conclusion / Q&A | 1 min | Summary and limitations |

---

## 23. Team Responsibilities

### Student 1: **[Name]**

Main responsibilities:

- [ ] Download and inspect DEBS dataset
- [ ] Implement raw data cleaning
- [ ] Implement metadata loading
- [ ] Implement stream replay
- [ ] Prepare dataset section for report
- [ ] Support live demo

### Student 2: **[Name]**

Main responsibilities:

- [ ] Implement Spark Structured Streaming job
- [ ] Implement running analysis
- [ ] Implement heat map analysis
- [ ] Implement dashboard
- [ ] Prepare implementation/results section for report
- [ ] Support live demo

Shared responsibilities:

- [ ] Testing
- [ ] Report writing
- [ ] Presentation preparation
- [ ] Demo rehearsal
- [ ] Code cleanup
- [ ] Final submission

---

## 24. Development Roadmap

### Phase 1: Project Setup

Status: **[Not started / In progress / Done]**

Tasks:

- [ ] Create repository structure
- [ ] Create virtual environment
- [ ] Install dependencies
- [ ] Verify Java 17
- [ ] Verify PySpark
- [ ] Add `.gitignore`
- [ ] Add README

---

### Phase 2: Fake Data Prototype

Status: **[Not started / In progress / Done]**

Tasks:

- [ ] Create small fake sensor CSV
- [ ] Implement minimal replay script
- [ ] Implement minimal Spark streaming job
- [ ] Compute events per sensor
- [ ] Write output stream
- [ ] Verify that the streaming pipeline works

---

### Phase 3: DEBS Data Integration

Status: **[Not started / In progress / Done]**

Tasks:

- [ ] Download raw DEBS sensor data
- [ ] Download metadata
- [ ] Understand file format
- [ ] Apply correct schema
- [ ] Clean first small subset
- [ ] Join with metadata
- [ ] Save cleaned subset
- [ ] Test replay with subset

---

### Phase 4: Running Analysis

Status: **[Not started / In progress / Done]**

Tasks:

- [ ] Convert speed units
- [ ] Classify intensity
- [ ] Compute distance approximation
- [ ] Compute current running statistics
- [ ] Compute aggregate running statistics
- [ ] Test with one player
- [ ] Extend to all players

---

### Phase 5: Heat Map

Status: **[Not started / In progress / Done]**

Tasks:

- [ ] Define field boundaries
- [ ] Define 8 x 13 grid
- [ ] Assign positions to grid cells
- [ ] Compute time per player per cell
- [ ] Compute percentages
- [ ] Visualize heat map

---

### Phase 6: Optional Possession Proxy

Status: **[Optional / Not started / In progress / Done]**

Tasks:

- [ ] Identify ball sensor
- [ ] Compute ball-player distance
- [ ] Assign closest player
- [ ] Add 1 metre threshold
- [ ] Add acceleration threshold if feasible
- [ ] Aggregate by player and team

---

### Phase 7: Dashboard and Demo

Status: **[Not started / In progress / Done]**

Tasks:

- [ ] Read Spark output files
- [ ] Plot running statistics
- [ ] Plot heat map
- [ ] Add auto-refresh
- [ ] Prepare demo mode
- [ ] Prepare fallback screenshots

---

### Phase 8: Report and Presentation

Status: **[Not started / In progress / Done]**

Tasks:

- [ ] Write introduction
- [ ] Describe DEBS dataset
- [ ] Explain preprocessing
- [ ] Explain streaming architecture
- [ ] Present analytics
- [ ] Discuss results
- [ ] Discuss limitations
- [ ] Prepare slides
- [ ] Rehearse live demo

---

## 25. Running the Full Project

### Option A: Full Demo Pipeline

Terminal 1:

```bash
python main.py
```

Terminal 2:

```bash
python src/replay_full_game.py --demo
```

Terminal 3:

```bash
streamlit run src/dashboard.py
```

### Option B: Cleaning Only

```bash
python src/clean_data.py
```

### Option C: Replay Only

```bash
python src/replay_full_game.py --demo
```

### Option D: Dashboard Only

```bash
streamlit run src/dashboard.py
```

---

## 26. Expected Output

Spark should write analytics results to:

```text
data/output/
```

Possible output folders:

```text
data/output/running_current/
data/output/running_aggregate_1min/
data/output/running_aggregate_5min/
data/output/running_aggregate_20min/
data/output/heatmap_8x13/
data/output/possession/
```

Example running analysis output:

```text
ts_start,ts_stop,player_id,intensity,distance,speed
10753295594424116,10753295694424116,player_1,trot,2.7,9.8
```

Example heat map output:

```text
ts,player_id,cell_x1,cell_y1,cell_x2,cell_y2,percent_time_in_cell
10753295694424116,player_1,0,-33960,6560,-28734,14.2
```

---

## 27. Troubleshooting

### Problem: Java version error

Check Java:

```bash
java -version
```

Recommended:

```text
Java 17
```

If Java 21 causes Spark errors, install Java 17 and set `JAVA_HOME`.

---

### Problem: PySpark cannot start

Try:

```bash
pip install --upgrade pyspark
```

Then test:

```bash
python -c "import pyspark; print(pyspark.__version__)"
```

---

### Problem: Stream does not process files

Check that files are being written to:

```text
data/stream_input/
```

Check that Spark schema matches the input columns.

Delete old checkpoints:

```bash
rm -rf checkpoints/*
```

Windows:

```powershell
Remove-Item checkpoints/* -Recurse -Force
```

---

### Problem: Dashboard does not update

Check that output files are being written to:

```text
data/output/
```

Restart Streamlit:

```bash
streamlit run src/dashboard.py
```

---

### Problem: Demo is too slow

Decrease:

```python
REPLAY_SLEEP_SECONDS
```

or increase:

```python
REPLAY_BATCH_SIZE
```

inside:

```text
src/config.py
```

---

### Problem: Raw dataset is too large

Use a smaller subset for development:

```text
first 1-5 minutes of the first half
```

Then scale up after the pipeline works.

---

## 28. Limitations

Current limitations:

- The stream is reconstructed from stored timestamped data.
- The demo may use a subset of the full dataset for stability.
- The original DEBS output frequency is reduced for a practical classroom demo.
- Ball possession is simplified unless full hit detection is implemented.
- Shot-on-goal detection is optional and may not be implemented.
- Dashboard visualizations are designed for demonstration, not production.

---

## 29. Future Work

Possible extensions:

- Use Kafka instead of file-based stream replay.
- Implement the full DEBS ball possession query.
- Implement shot-on-goal detection.
- Support all heat map grid resolutions.
- Compare results with the official reference statistics.
- Deploy Spark on AWS EC2.
- Add a real-time soccer field visualization.

---

## 30. References

Planned references for the final report:

```text
[1] DEBS 2013 Grand Challenge: Soccer Monitoring
[2] Apache Spark Structured Streaming Documentation
[3] Structured Streaming: A Declarative API for Real-Time Applications in Apache Spark
[4] DEBS 2013 Grand Challenge paper
[5] Soccer movement and tracking data analysis literature
```

---

## 31. Current Project Status

Last updated: **[Insert Date]**

| Component | Status |
|---|---|
| Repository setup | [Not started / In progress / Done] |
| Python environment | [Not started / In progress / Done] |
| PySpark test | [Not started / In progress / Done] |
| Fake data stream | [Not started / In progress / Done] |
| DEBS dataset download | [Not started / In progress / Done] |
| Metadata loading | [Not started / In progress / Done] |
| Data cleaning | [Not started / In progress / Done] |
| Spark streaming job | [Not started / In progress / Done] |
| Running analysis | [Not started / In progress / Done] |
| Heat map | [Not started / In progress / Done] |
| Possession proxy | [Optional / Not started / In progress / Done] |
| Dashboard | [Not started / In progress / Done] |
| Report | [Not started / In progress / Done] |
| Presentation | [Not started / In progress / Done] |
| Live demo | [Not started / In progress / Done] |

---

## 32. Authors

**[Student 1 Name]**  
Email: **[Student 1 Email]**

**[Student 2 Name]**  
Email: **[Student 2 Email]**

University of Basel  
Distributed Information Systems Spring 2026