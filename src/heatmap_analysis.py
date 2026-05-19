import math
from collections import defaultdict
from typing import Dict, List, Tuple

class HeatmapAnalyzer:
    def __init__(self, x_min: float, x_max: float, y_min: float, y_max: float, cols: int = 13, rows: int = 8):
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.cols = cols  
        self.rows = rows  
        
        # CHANGED: Maintain a separate grid for every individual sensor ID
        self.grids = defaultdict(lambda: [[0 for _ in range(cols)] for _ in range(rows)])

    def get_cell(self, x: float, y: float) -> Tuple[int, int]:
        x_pct = (x - self.x_min) / (self.x_max - self.x_min)
        y_pct = (y - self.y_min) / (self.y_max - self.y_min)

        x_pct = max(0.0, min(0.9999, x_pct))
        y_pct = max(0.0, min(0.9999, y_pct))

        col_idx = math.floor(x_pct * self.cols)
        row_idx = math.floor(y_pct * self.rows)

        return row_idx, col_idx

    def update_from_positions(self, positions: List[Dict]):
        for pos in positions:
            x = pos.get("x")
            y = pos.get("y")
            sid = pos.get("sid")
            
            if x is not None and y is not None and sid is not None:
                row_idx, col_idx = self.get_cell(x, y)
                self.grids[sid][row_idx][col_idx] += 1

    def get_grids(self) -> Dict[int, List[List[int]]]:
        return dict(self.grids)