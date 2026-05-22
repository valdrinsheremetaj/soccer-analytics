"""

This module provides a small stateful analyzer that converts player or ball
positions into smooth heatmap visit counts. A separate heatmap grid is
maintained for each sensor ID.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Hashable, Mapping, Sequence
from typing import DefaultDict, List, Optional, Tuple


DEFAULT_COLUMNS = 80
DEFAULT_ROWS = 50
DEFAULT_KERNEL_RADIUS_CELLS = 5
DEFAULT_KERNEL_SIGMA_CELLS = 2.0
MAX_GRID_PERCENTAGE = 0.9999
MIN_KERNEL_WEIGHT = 0.01

Grid = List[List[float]]
SensorId = Hashable
Position = Mapping[str, object]
KernelPoint = Tuple[int, int, float]


class HeatmapAnalyzer:
    """Builds per-sensor smooth heatmap grids from x/y position samples.

    Instead of increasing only one grid cell, each position adds a small
    Gaussian kernel around the current cell. This creates a continuous football
    heatmap effect when rendered in the dashboard.
    """

    def __init__(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        cols: int = DEFAULT_COLUMNS,
        rows: int = DEFAULT_ROWS,
        kernel_radius_cells: int = DEFAULT_KERNEL_RADIUS_CELLS,
        kernel_sigma_cells: float = DEFAULT_KERNEL_SIGMA_CELLS,
    ) -> None:
        """Initializes the heatmap analyzer.

        Args:
            x_min: Minimum x-coordinate of the analyzed area.
            x_max: Maximum x-coordinate of the analyzed area.
            y_min: Minimum y-coordinate of the analyzed area.
            y_max: Maximum y-coordinate of the analyzed area.
            cols: Number of columns in the heatmap grid.
            rows: Number of rows in the heatmap grid.
            kernel_radius_cells: Radius around the center cell to update.
            kernel_sigma_cells: Gaussian smoothing strength in grid cells.

        Raises:
            ValueError: If bounds, grid size, or kernel settings are invalid.
        """
        self._validate_bounds(x_min, x_max, y_min, y_max)
        self._validate_grid_size(cols, rows)
        self._validate_kernel(kernel_radius_cells, kernel_sigma_cells)

        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.cols = cols
        self.rows = rows
        self.kernel_radius_cells = kernel_radius_cells
        self.kernel_sigma_cells = kernel_sigma_cells

        self._kernel = self._create_kernel()
        self._grids: DefaultDict[SensorId, Grid] = defaultdict(self._create_empty_grid)

    def get_cell(self, x: float, y: float) -> Tuple[int, int]:
        """Returns the grid cell containing the given position."""
        x_percentage = self._normalize_coordinate(x, self.x_min, self.x_max)
        y_percentage = self._normalize_coordinate(y, self.y_min, self.y_max)

        column_index = math.floor(x_percentage * self.cols)
        row_index = math.floor(y_percentage * self.rows)

        return row_index, column_index

    def update_from_positions(self, positions: Sequence[Position]) -> None:
        """Updates heatmap grids from a sequence of position dictionaries."""
        for position in positions:
            sensor_id = position.get("sid")
            x_coordinate = self._to_float(position.get("x"))
            y_coordinate = self._to_float(position.get("y"))

            if sensor_id is None or x_coordinate is None or y_coordinate is None:
                continue

            row_index, column_index = self.get_cell(x_coordinate, y_coordinate)
            self._add_kernel(sensor_id, row_index, column_index)

    def get_grids(self) -> dict[SensorId, Grid]:
        """Returns the current heatmap grids."""
        return dict(self._grids)

    def _add_kernel(
        self,
        sensor_id: SensorId,
        center_row: int,
        center_column: int,
    ) -> None:
        """Adds the precomputed smoothing kernel around one position."""
        grid = self._grids[sensor_id]

        for row_offset, column_offset, weight in self._kernel:
            row_index = center_row + row_offset
            column_index = center_column + column_offset

            if not 0 <= row_index < self.rows:
                continue

            if not 0 <= column_index < self.cols:
                continue

            grid[row_index][column_index] += weight

    def _create_kernel(self) -> list[KernelPoint]:
        """Creates a Gaussian kernel as relative cell offsets."""
        kernel: list[KernelPoint] = []
        denominator = 2.0 * self.kernel_sigma_cells * self.kernel_sigma_cells

        for row_offset in range(
            -self.kernel_radius_cells,
            self.kernel_radius_cells + 1,
        ):
            for column_offset in range(
                -self.kernel_radius_cells,
                self.kernel_radius_cells + 1,
            ):
                distance_squared = row_offset**2 + column_offset**2
                weight = math.exp(-distance_squared / denominator)

                if weight < MIN_KERNEL_WEIGHT:
                    continue

                kernel.append((row_offset, column_offset, weight))

        return kernel

    def _create_empty_grid(self) -> Grid:
        """Creates an empty heatmap grid filled with zeros."""
        return [[0.0 for _ in range(self.cols)] for _ in range(self.rows)]

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

    @staticmethod
    def _validate_kernel(
        kernel_radius_cells: int,
        kernel_sigma_cells: float,
    ) -> None:
        """Validates Gaussian kernel settings."""
        if kernel_radius_cells < 0:
            raise ValueError("kernel_radius_cells must not be negative.")

        if kernel_sigma_cells <= 0:
            raise ValueError("kernel_sigma_cells must be greater than 0.")