"""

This script simulates a live stream by copying precomputed chunk folders into
the stream input directory one after another. Each copied chunk receives a fresh
modification timestamp so Spark can process the files in replay order.
"""

import logging
import os
import shutil
import time
from pathlib import Path

from src.config import CHUNKED_FULL_GAME_PATH

LOGGER = logging.getLogger(__name__)

STREAM_INPUT_PATH = Path("data/stream_input")
REPLAY_SLEEP_SECONDS = 1.0
CHUNK_DIRECTORY_PREFIX = "chunkId="


def _clear_directory(directory_path: Path) -> None:
    """Remove all files and folders inside a directory.

    Args:
        directory_path: Directory whose contents should be deleted.
    """
    for item_path in directory_path.iterdir():
        if item_path.is_dir():
            shutil.rmtree(item_path)
        else:
            item_path.unlink()


def _get_chunk_id(chunk_path: Path) -> int:
    """Extract the numeric chunk ID from a Spark partition directory name.

    Args:
        chunk_path: Path with a name such as ``chunkId=12``.

    Returns:
        The numeric chunk ID.

    Raises:
        ValueError: If the directory name does not contain a valid chunk ID.
    """
    return int(chunk_path.name.split("=", maxsplit=1)[1])


def _get_sorted_chunk_paths(source_path: Path) -> list[Path]:
    """Return all chunk directories sorted by their numeric chunk ID.

    Args:
        source_path: Directory containing Spark partition folders.

    Returns:
        A list of chunk directories ordered by match time.
    """
    chunk_paths = [
        path
        for path in source_path.iterdir()
        if path.is_dir() and path.name.startswith(CHUNK_DIRECTORY_PREFIX)
    ]

    return sorted(chunk_paths, key=_get_chunk_id)


def _refresh_modification_times(path: Path) -> None:
    """Set fresh modification times for a copied chunk and its files.

    Spark file streaming uses file metadata when detecting new input files.
    Updating the timestamps after copying prevents Spark from seeing the
    original Parquet timestamps and helps it process chunks in replay order.

    Args:
        path: Copied chunk directory whose timestamps should be refreshed.
    """
    current_time = time.time()
    os.utime(path, (current_time, current_time))

    for child_path in path.rglob("*"):
        os.utime(child_path, (current_time, current_time))


def replay_full_game() -> None:
    """Replay the full game by copying chunk folders into the stream input path.

    Raises:
        FileNotFoundError: If the chunked data directory does not exist.
    """
    source_path = Path(CHUNKED_FULL_GAME_PATH)

    if not source_path.exists():
        raise FileNotFoundError(f"Chunked data folder not found: {source_path}")

    STREAM_INPUT_PATH.mkdir(parents=True, exist_ok=True)
    _clear_directory(STREAM_INPUT_PATH)

    chunk_paths = _get_sorted_chunk_paths(source_path)

    LOGGER.info("Found %d chunks.", len(chunk_paths))
    LOGGER.info("Starting replay.")

    for chunk_path in chunk_paths:
        target_path = STREAM_INPUT_PATH / chunk_path.name

        shutil.copytree(chunk_path, target_path)
        _refresh_modification_times(target_path)

        LOGGER.info("Replayed %s.", chunk_path.name)
        time.sleep(REPLAY_SLEEP_SECONDS)

    LOGGER.info("Replay finished.")


def main() -> None:
    """Configure logging and start the replay."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    replay_full_game()


if __name__ == "__main__":
    main()
