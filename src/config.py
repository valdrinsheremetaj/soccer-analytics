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

RAW_FULL_GAME_PATH = "data/raw/full-game"
CLEAN_FULL_GAME_PATH = "data/processed/full-game-clean"
CHUNKED_FULL_GAME_PATH = "data/processed/full-game-chunked"


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
