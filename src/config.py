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



FIELD_X_MIN = -52489
FIELD_X_MAX = 52489
FIELD_Y_MIN = -33965
FIELD_Y_MAX = 33965

BALL_IDS_BY_HALF = {
    1: {4, 8, 10},
    2: {4, 8, 10, 12},
}


TEAM_A_PLAYERS = {
    "Nick Gertje": {
        "feet": [13, 14],
        "extra": [97, 98],
    },
    "Dennis Dotterweich": {
        "feet": [47, 16],
        "extra": [],
    },
    "Niklas Waelzlein": {
        "feet": [49, 88],
        "extra": [],
    },
    "Wili Sommer": {
        "feet": [19, 52],
        "extra": [],
    },
    "Philipp Harlass": {
        "feet": [53, 54],
        "extra": [],
    },
    "Roman Hartleb": {
        "feet": [23, 24],
        "extra": [],
    },
    "Erik Engelhardt": {
        "feet": [57, 58],
        "extra": [],
    },
    "Sandro Schneider": {
        "feet": [59, 28],
        "extra": [],
    },
}


TEAM_B_PLAYERS = {
    "Leon Krapf": {
        "feet": [61, 62],
        "extra": [99, 100],
    },
    "Kevin Baer": {
        "feet": [63, 64],
        "extra": [],
    },
    "Luca Ziegler": {
        "feet": [65, 66],
        "extra": [],
    },
    "Ben Mueller": {
        "feet": [67, 68],
        "extra": [],
    },
    "Vale Reitstetter": {
        "feet": [69, 38],
        "extra": [],
    },
    "Christopher Lee": {
        "feet": [71, 40],
        "extra": [],
    },
    "Leon Heinze": {
        "feet": [73, 74],
        "extra": [],
    },
    "Leo Langhans": {
        "feet": [75, 44],
        "extra": [],
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
        StructField("matchSecond", IntegerType(), True),
    ]
)

CHUNKED_SCHEMA = StructType(
    CLEAN_SCHEMA.fields + [StructField("chunkId", IntegerType(), True)]
)


# start_ts = df.agg({"ts": "min"}).collect()[0][0]
# end_ts = df.agg({"ts": "max"}).collect()[0][0]
