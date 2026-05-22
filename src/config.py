from pyspark.sql import SparkSession 
from pyspark.sql.types import *
from pyspark.sql.functions import col, floor, lit, min as spark_min


FIRST_HALF_START_TS = 10753295594424116
FIRST_HALF_END_TS = 12557295594424116

SECOND_HALF_START_TS = 13086639146403495
SECOND_HALF_END_TS = 14879639146403495

GAME_START_TS = FIRST_HALF_START_TS
GAME_END_TS = SECOND_HALF_END_TS

TS_PER_SECOND = 1_000_000_000_000

CHUNK_SECONDS = 1
REPLAY_SLEEP_SECONDS = 1

RAW_FULL_GAME_PATH = "data/raw/full-game"
CLEAN_FULL_GAME_PATH = "data/processed/full-game-clean"
CHUNKED_FULL_GAME_PATH = "data/processed/full-game-chunked"



FIELD_X_MIN = -68000
FIELD_X_MAX = 68000
FIELD_Y_MIN = -32500
FIELD_Y_MAX = 32500

BALL_SENSOR_IDS = [4, 8, 10, 12]

BALL_IDS_BY_HALF = {
    1: {4, 8, 10},
    2: {4, 8, 10, 12},
}


TEAM_A_PLAYERS = {
    "Nick Gertje": {
        "feet": [13, 14],
        "extra": [97, 98],
        "role": "Goalkeeper"
    },
    "Dennis Dotterweich": {
        "feet": [47, 16],
        "extra": [],
        "role": "Defender"
    },
    "Niklas Waelzlein": {
        "feet": [49, 88],
        "extra": [],
        "role": "Defender"
    },
    "Wili Sommer": {
        "feet": [19, 52],
        "extra": [],
        "role": "Defender"
    },
    "Philipp Harlass": {
        "feet": [53, 54],
        "extra": [],
        "role": "Defender"
    },
    "Roman Hartleb": {
        "feet": [23, 24],
        "extra": [],
        "role": "Midfielder"
    },
    "Erik Engelhardt": {
        "feet": [57, 58],
        "extra": [],
        "role": "Forward"
    },
    "Sandro Schneider": {
        "feet": [59, 28],
        "extra": [],
        "role": "Forward"
    },
}


TEAM_B_PLAYERS = {
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
        "role": "Defender"
    },
    "Ben Mueller": {
        "feet": [67, 68],
        "extra": [],
        "role": "Midfielder"
    },
    "Vale Reitstetter": {
        "feet": [69, 38],
        "extra": [],
        "role": "Midfielder"
    },
    "Christopher Lee": {
        "feet": [71, 40],
        "extra": [],
        "role": "Defender"
    },
    "Leon Heinze": {
        "feet": [73, 74],
        "extra": [],
        "role": "Forward"
    },
    "Leo Langhans": {
        "feet": [75, 44],
        "extra": [],
        "role": "Forward"
    },
}


REFEREE = {
    "Referee": {
        "feet": [105, 106],
        "extra": [],
    }
}


RAW_SCHEMA = StructType([
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
])

CLEAN_SCHEMA = StructType(
    RAW_SCHEMA.fields + [
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

CHUNKED_SCHEMA = StructType(
    CLEAN_SCHEMA.fields + [StructField("chunkId", IntegerType(), True)]
)


# start_ts = df.agg({"ts": "min"}).collect()[0][0]
# end_ts = df.agg({"ts": "max"}).collect()[0][0]
