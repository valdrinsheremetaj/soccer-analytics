from pathlib import Path
import shutil
import time

from src.config import CHUNKED_FULL_GAME_PATH, REPLAY_SLEEP_SECONDS

STREAM_INPUT_PATH = Path("data/stream_input")


def replay_full_game() -> None:
    source_path = Path(CHUNKED_FULL_GAME_PATH)

    if not source_path.exists():
        raise FileNotFoundError(f"Chunked data folder not found: {source_path}")

    STREAM_INPUT_PATH.mkdir(parents=True, exist_ok=True)

    # clean old stream input
    for item in STREAM_INPUT_PATH.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    chunks = sorted(
        [p for p in source_path.iterdir() if p.is_dir() and p.name.startswith("chunkId=")],
        key=lambda p: int(p.name.split("=")[1])
    )

    print(f"Found {len(chunks)} chunks.")
    print("Starting replay...")

    for chunk in chunks:
        target = STREAM_INPUT_PATH / chunk.name
        shutil.copytree(chunk, target)

        print(f"Replayed {chunk.name}")
        time.sleep(REPLAY_SLEEP_SECONDS)

    print("Replay finished.")


if __name__ == "__main__":
    replay_full_game()