# Soccer Analytics

Real-time soccer tracking demo using the **DEBS 2013 Grand Challenge Soccer Monitoring** dataset, **Apache Spark Structured Streaming**, and a **Streamlit** dashboard.

The project cleans raw full-game tracking data, splits it into one-second chunks, replays those chunks as a simulated live stream, processes them with Spark, and visualizes live positions, running statistics, heatmaps, possession estimates, pressure, and momentum indicators.

## Features

- clean and normalize raw DEBS tracking data
- convert timestamps, coordinates, speed, and acceleration into usable units
- split cleaned data into replayable match-time chunks
- simulate a live stream from static match files
- run Spark Structured Streaming analysis
- show live player, ball, and referee positions in Streamlit
- show rolling running statistics, heatmaps, possession, pressure, and momentum

## Project Structure

```text
.
├── data/
│   ├── raw/
│   │   ├── full-game/              # raw DEBS full-game tracking data
│   │   └── referee-events/         # optional referee/event metadata
│   ├── metadata/                   # optional match metadata
│   ├── processed/                  # cleaned and chunked data
│   ├── stream_input/               # replayed chunks for Spark
│   └── output/                     # live JSON output for dashboard
├── src/
│   ├── clean_data.py               # clean raw data
│   ├── split_data.py               # split cleaned data into chunks
│   ├── replay_full_game.py         # replay chunks as stream input
│   ├── demo_streaming_job.py       # Spark streaming analysis
│   ├── dashboard.py                # Streamlit dashboard
│   ├── statistics_tab.py           # dashboard statistics tab
│   ├── heatmap_analysis.py         # heatmap logic
│   └── config.py                   # paths, schemas, constants, metadata
├── run_all.py                      # starts the complete local demo
├── main.py                         # preprocessing only
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Requirements

- Python 3.10+
- Java 17
- pip / virtualenv
- Spark is installed through PySpark from `requirements.txt`

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Check that Java is available:

```bash
java -version
```

## Data Setup

Place the DEBS full-game tracking data here:

```text
data/raw/full-game/
```

Optional metadata such as ball possession, game interruptions, and shot events can be placed in:

```text
data/raw/referee-events/
```

The default paths are configured in `src/config.py`.

## Run the Full Demo

The easiest way is:

```bash
python run_all.py
```

This will:

1. check whether raw data exists,
2. clean the raw full-game data if needed,
3. split the cleaned data into one-second chunks if needed,
4. start the Spark streaming job,
5. replay the game chunks,
6. start the Streamlit dashboard.

Open the Streamlit URL printed in the terminal, usually:

```text
http://localhost:8501
```

Stop everything with:

```text
CTRL+C
```

## Run Steps Manually

Clean the raw data:

```bash
python -m src.clean_data
```

Split cleaned data into chunks:

```bash
python -m src.split_data
```

Start the replay:

```bash
python -m src.replay_full_game
```

In another terminal, start the Spark streaming job:

```bash
python -m src.demo_streaming_job
```



In another terminal, start the dashboard:

```bash
streamlit run src/dashboard.py
```

## Preprocessing Only

To only clean and split the data:

```bash
python main.py
```

## Docker

Build and start the container:

```bash
docker compose up --build
```

Then open a shell inside the container if needed:

```bash
docker exec -it soccer-analytics bash
```

Inside the container, run the same commands as above, for example:

```bash
python3 run_all.py
```

The Streamlit dashboard is exposed on:

```text
http://localhost:8501
```

## Notes

- Cleaned data is written to `data/processed/full-game-clean`.
- Chunked replay data is written to `data/processed/full-game-chunked`.
- Streaming input is read from `data/stream_input`.
- Dashboard output files are written to `data/output/live_positions`.
- The current chunk size is one second and can be changed in `src/config.py`.
