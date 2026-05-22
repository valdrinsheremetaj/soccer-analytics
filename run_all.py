from pathlib import Path
import subprocess
import sys
import time
import os
import signal

from src.config import (
    RAW_FULL_GAME_PATH,
    CLEAN_FULL_GAME_PATH,
    CHUNKED_FULL_GAME_PATH,
)

def path_has_data(path: str) -> bool:
    p = Path(path)

    print(f"Checking raw path: {p.resolve()}")

    if not p.exists():
        return False

    if p.is_file():
        return p.stat().st_size > 0

    if p.is_dir():
        return any(
            child.is_file() and child.stat().st_size > 0
            for child in p.rglob("*")
        )

    return False

def chunked_data_exists() -> bool:
    p = Path(CHUNKED_FULL_GAME_PATH)
    return p.exists() and any(p.glob("chunkId=*"))

def run_blocking(name: str, command: list[str]) -> None:
    print(f"\n=== {name} ===")
    result = subprocess.run(command)
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {result.returncode}")

def start_process(name: str, command: list[str]) -> subprocess.Popen:
    print(f"\nStarting {name}: {' '.join(command)}")

    # Mac/Linux: start in separate process group so we can kill it cleanly
    return subprocess.Popen(
        command,
        start_new_session=True,
    )

def stop_processes(processes: list[subprocess.Popen]) -> None:
    print("\nStopping all running processes...")

    for p in processes:
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass

    time.sleep(2)

    for p in processes:
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass

def main() -> None:
    processes: list[subprocess.Popen] = []

    raw_exists = path_has_data(RAW_FULL_GAME_PATH)
    clean_exists = path_has_data(CLEAN_FULL_GAME_PATH)
    chunks_exist = chunked_data_exists()

    if not raw_exists:
        raise FileNotFoundError(
            f"Raw data not found in {RAW_FULL_GAME_PATH}. "
            "Put the full game data there first."
        )

    if not clean_exists:
        run_blocking("Cleaning full game data", [sys.executable, "-m", "src.clean_data"])
    else:
        print("Clean data already exists. Skipping cleaning.")

    if not chunks_exist:
        run_blocking("Splitting cleaned data into chunks", [sys.executable, "-m", "src.split_data"])
    else:
        print("Chunked data already exists. Skipping splitting.")

    try:
        analysis = start_process(
            "Spark streaming analysis",
            [sys.executable, "-m", "src.demo_streaming_job"],
        )
        processes.append(analysis)

        # Give Spark a moment to create/check the stream input folder.
        time.sleep(3)

        replay = start_process(
            "Replay full game",
            [sys.executable, "-m", "src.replay_full_game"],
        )
        processes.append(replay)

        dashboard = start_process(
            "Streamlit dashboard",
            [sys.executable, "-m", "streamlit", "run", "src/dashboard.py"],
        )
        processes.append(dashboard)

        print("\nEverything is running.")
        print("Open the Streamlit URL shown above.")
        print("Press CTRL+C here to stop all processes.")

        while True:
            time.sleep(1)

            # If analysis or dashboard crashes, stop everything.
            for p in processes:
                if p.poll() is not None and p is not replay:
                    raise RuntimeError("A required process stopped unexpectedly.")

    except KeyboardInterrupt:
        pass
    finally:
        stop_processes(processes)

if __name__ == "__main__":
    main()