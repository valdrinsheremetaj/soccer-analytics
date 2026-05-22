"""

This module centralizes constants, file paths, player metadata, sensor IDs, and
Spark schemas used by the preprocessing, replay, and streaming jobs.
"""

from typing import Dict, Final, List, Set, TypedDict

from pyspark.sql.types import DoubleType, IntegerType, LongType, StructField, StructType


class PlayerMetadata(TypedDict):
    """Metadata describing one player and their assigned sensor IDs."""

    feet: List[int]
    extra: List[int]
    role: str


class RefereeMetadata(TypedDict):
    """Metadata describing the referee and their assigned sensor IDs."""

    feet: List[int]
    extra: List[int]


# Match timestamp boundaries.
#
# Timestamps in the DEBS 2013 dataset are expressed in picoseconds. The match is
# split into two valid playing intervals; records outside these intervals are
# ignored during cleaning.
FIRST_HALF_START_TS: Final[int] = 10_753_295_594_424_116
FIRST_HALF_END_TS: Final[int] = 12_557_295_594_424_116

SECOND_HALF_START_TS: Final[int] = 13_086_639_146_403_495
SECOND_HALF_END_TS: Final[int] = 14_879_639_146_403_495

GAME_START_TS: Final[int] = FIRST_HALF_START_TS
GAME_END_TS: Final[int] = SECOND_HALF_END_TS

TS_PER_SECOND: Final[int] = 1_000_000_000_000


# Replay and chunking settings.
CHUNK_SECONDS: Final[int] = 1
REPLAY_SLEEP_SECONDS: Final[int] = 1


# Data paths.
RAW_FULL_GAME_PATH: Final[str] = "data/raw/full-game"
CLEAN_FULL_GAME_PATH: Final[str] = "data/processed/full-game-clean"
CHUNKED_FULL_GAME_PATH: Final[str] = "data/processed/full-game-chunked"


# Field boundaries in the original dataset coordinate system.
FIELD_X_MIN: Final[int] = -68_000
FIELD_X_MAX: Final[int] = 68_000
FIELD_Y_MIN: Final[int] = -32_500
FIELD_Y_MAX: Final[int] = 32_500


# Sensor IDs.
BALL_SENSOR_IDS: Final[List[int]] = [4, 8, 10, 12]

BALL_IDS_BY_HALF: Final[Dict[int, Set[int]]] = {
    1: {4, 8, 10},
    2: {4, 8, 10, 12},
}


# Player metadata.
#
# Each player has two foot sensors and may have additional sensors. Roles are
# used by the dashboard and analysis logic for grouping/filtering players.
TEAM_A_PLAYERS: Final[Dict[str, PlayerMetadata]] = {
    "Nick Gertje": {
        "feet": [13, 14],
        "extra": [97, 98],
        "role": "Goalkeeper",
    },
    "Dennis Dotterweich": {
        "feet": [47, 16],
        "extra": [],
        "role": "Defender",
    },
    "Niklas Waelzlein": {
        "feet": [49, 88],
        "extra": [],
        "role": "Defender",
    },
    "Wili Sommer": {
        "feet": [19, 52],
        "extra": [],
        "role": "Defender",
    },
    "Philipp Harlass": {
        "feet": [53, 54],
        "extra": [],
        "role": "Defender",
    },
    "Roman Hartleb": {
        "feet": [23, 24],
        "extra": [],
        "role": "Midfielder",
    },
    "Erik Engelhardt": {
        "feet": [57, 58],
        "extra": [],
        "role": "Forward",
    },
    "Sandro Schneider": {
        "feet": [59, 28],
        "extra": [],
        "role": "Forward",
    },
}

TEAM_B_PLAYERS: Final[Dict[str, PlayerMetadata]] = {
    "Leon Krapf": {
        "feet": [61, 62],
        "extra": [99, 100],
        "role": "Goalkeeper",
    },
    "Kevin Baer": {
        "feet": [63, 64],
        "extra": [],
        "role": "Midfielder",
    },
    "Luca Ziegler": {
        "feet": [65, 66],
        "extra": [],
        "role": "Defender",
    },
    "Ben Mueller": {
        "feet": [67, 68],
        "extra": [],
        "role": "Midfielder",
    },
    "Vale Reitstetter": {
        "feet": [69, 38],
        "extra": [],
        "role": "Midfielder",
    },
    "Christopher Lee": {
        "feet": [71, 40],
        "extra": [],
        "role": "Defender",
    },
    "Leon Heinze": {
        "feet": [73, 74],
        "extra": [],
        "role": "Forward",
    },
    "Leo Langhans": {
        "feet": [75, 44],
        "extra": [],
        "role": "Forward",
    },
}

REFEREE: Final[Dict[str, RefereeMetadata]] = {
    "Referee": {
        "feet": [105, 106],
        "extra": [],
    },
}


# Spark schemas.
RAW_SCHEMA: Final[StructType] = StructType(
    [
        StructField("sid", IntegerType(), True),
        StructField("ts", LongType(), True),
        StructField("x", IntegerType(), True),
        StructField("y", IntegerType(), True),
        StructField("z", IntegerType(), True),
        StructField("v_abs", LongType(), True),
        StructField("a_abs", LongType(), True),
        StructField("vx", IntegerType(), True),
        StructField("vy", IntegerType(), True),
        StructField("vz", IntegerType(), True),
        StructField("ax", IntegerType(), True),
        StructField("ay", IntegerType(), True),
        StructField("az", IntegerType(), True),
    ]
)

# Column names such as "matchSecond" are kept unchanged because other pipeline
# components already depend on this data contract.
CLEAN_SCHEMA: Final[StructType] = StructType(
    RAW_SCHEMA.fields
    + [
        StructField("half", IntegerType(), True),
        StructField("matchSecond", DoubleType(), True),
        StructField("x_m", DoubleType(), True),
        StructField("y_m", DoubleType(), True),
        StructField("z_m", DoubleType(), True),
        StructField("speed_m_s", DoubleType(), True),
        StructField("speed_kmh", DoubleType(), True),
        StructField("acceleration_m_s2", DoubleType(), True),
    ]
)

CHUNKED_SCHEMA: Final[StructType] = StructType(
    CLEAN_SCHEMA.fields
    + [
        StructField("chunkId", IntegerType(), True),
    ]
)
