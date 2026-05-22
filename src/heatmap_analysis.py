"""

This module provides a small stateful analyzer that converts player or ball
positions into grid-cell visit counts. A separate heatmap grid is maintained
for each sensor ID.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Hashable, Mapping, Sequence
from typing import DefaultDict, List, Optional, Tuple


DEFAULT_COLUMNS = 13
DEFAULT_ROWS = 8
MAX_GRID_PERCENTAGE = 0.9999

Grid = List[List[int]]
SensorId = Hashable
Position = Mapping[str, object]


class HeatmapAnalyzer:
    """Builds per-sensor heatmap grids from x/y position samples.

    The field is split into a configurable number of columns and rows. Each
    incoming position is mapped to one grid cell, and the corresponding count
    is increased for that position's sensor ID.

    Attributes:
        x_min: Minimum x-coordinate of the analyzed area.
        x_max: Maximum x-coordinate of the analyzed area.
        y_min: Minimum y-coordinate of the analyzed area.
        y_max: Maximum y-coordinate of the analyzed area.
        cols: Number of grid columns.
        rows: Number of grid rows.
    """

    def __init__(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        cols: int = DEFAULT_COLUMNS,
        rows: int = DEFAULT_ROWS,
    ) -> None:
        """Initializes the heatmap analyzer.

        Args:
            x_min: Minimum x-coordinate of the analyzed area.
            x_max: Maximum x-coordinate of the analyzed area.
            y_min: Minimum y-coordinate of the analyzed area.
            y_max: Maximum y-coordinate of the analyzed area.
            cols: Number of columns in the heatmap grid.
            rows: Number of rows in the heatmap grid.

        Raises:
            ValueError: If the coordinate bounds or grid size are invalid.
        """
        self._validate_bounds(x_min, x_max, y_min, y_max)
        self._validate_grid_size(cols, rows)

        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.cols = cols
        self.rows = rows

        self._grids: DefaultDict[SensorId, Grid] = defaultdict(self._create_empty_grid)

    def get_cell(self, x: float, y: float) -> Tuple[int, int]:
        """Returns the grid cell containing the given position.

        Coordinates outside the configured bounds are clamped to the closest
        valid heatmap cell.

        Args:
            x: X-coordinate in the same unit as the configured x-bounds.
            y: Y-coordinate in the same unit as the configured y-bounds.

        Returns:
            A tuple in the form ``(row_index, column_index)``.
        """
        x_percentage = self._normalize_coordinate(x, self.x_min, self.x_max)
        y_percentage = self._normalize_coordinate(y, self.y_min, self.y_max)

        column_index = math.floor(x_percentage * self.cols)
        row_index = math.floor(y_percentage * self.rows)

        return row_index, column_index

    def update_from_positions(self, positions: Sequence[Position]) -> None:
        """Updates heatmap grids from a sequence of position dictionaries.

        Each position is expected to contain ``x``, ``y``, and ``sid`` keys.
        Invalid or incomplete positions are skipped.

        Args:
            positions: Position records containing x/y coordinates and a
                sensor ID under the key ``sid``.
        """
        for position in positions:
            sensor_id = position.get("sid")
            x_coordinate = self._to_float(position.get("x"))
            y_coordinate = self._to_float(position.get("y"))

            if sensor_id is None or x_coordinate is None or y_coordinate is None:
                continue

            row_index, column_index = self.get_cell(x_coordinate, y_coordinate)
            self._grids[sensor_id][row_index][column_index] += 1

    def get_grids(self) -> dict[SensorId, Grid]:
        """Returns the current heatmap grids.

        Returns:
            A dictionary that maps each sensor ID to its heatmap grid.
        """
        return dict(self._grids)

    def _create_empty_grid(self) -> Grid:
        """Creates an empty heatmap grid filled with zeros."""
        return [[0 for _ in range(self.cols)] for _ in range(self.rows)]

    @staticmethod
    def _normalize_coordinate(value: float, minimum: float, maximum: float) -> float:
        """Normalizes and clamps a coordinate into the range [0.0, 0.9999]."""
        percentage = (value - minimum) / (maximum - minimum)
        return max(0.0, min(MAX_GRID_PERCENTAGE, percentage))

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        """Converts numeric-like values to float and rejects invalid values."""
        if value is None:
            return None

        try:
            converted_value = float(value)
        except (TypeError, ValueError):
            return None

        if math.isnan(converted_value) or math.isinf(converted_value):
            return None

        return converted_value

    @staticmethod
    def _validate_bounds(
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> None:
        """Validates coordinate bounds."""
        if x_min >= x_max:
            raise ValueError("x_min must be smaller than x_max.")

        if y_min >= y_max:
            raise ValueError("y_min must be smaller than y_max.")

    @staticmethod
    def _validate_grid_size(cols: int, rows: int) -> None:
        """Validates grid dimensions."""
        if cols <= 0:
            raise ValueError("cols must be greater than 0.")

        if rows <= 0:
            raise ValueError("rows must be greater than 0.")
