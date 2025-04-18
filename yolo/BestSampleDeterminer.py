from enum import Enum
from typing import List, Optional

# Constants from Java code
X_THRESHOLD = 4.0  # inches
Y_THRESHOLD = 4.0  # inches
NEIGHBOR_PENALTY = 3.0
MAX_REL_X = 7.0
X_MIN = 50.5
X_MAX = X_MIN + 30
MIN_REL_Y = 7.0  # Assuming this value based on context
MAX_REL_Y = 16.0  # Assuming this value based on context


class Alliance(Enum):
    RED = "RED"
    BLUE = "BLUE"


class SampleColor(Enum):
    BLUE = 0
    RED = 1
    YELLOW = 2


class Sample:
    """Sample class to represent detected elements"""

    def __init__(self, class_id: int, world_x: float, world_y: float, detection):
        self.x = world_x
        self.y = world_y
        # The original detection object so I can reference it later
        self.detection = detection

        # Map class_id to color
        if class_id == 0:
            self.color = SampleColor.BLUE
        elif class_id == 1:
            self.color = SampleColor.RED
        elif class_id == 2:
            self.color = SampleColor.YELLOW
        else:
            self.color = None


def determine_best_sample(samples: List[Sample], ALLOWED_COLORS, x_coord: float) -> Optional[Sample]:
    """
    Determine the best sample to pick up based on various criteria

    Args:
        samples: List of detected samples
        alliance: Current alliance (RED or BLUE)
        x_coord: Reference X coordinate

    Returns:
        The best sample to pick up, or None if no suitable sample found
    """

    best_sample = None
    best_coef = float('inf')

    print(f"Processing {len(samples)} samples. Allowed colors: {ALLOWED_COLORS}")

    for sample in samples:
        if sample is None:
            continue

        # Check if sample color is allowed
        sample_color_name = sample.color.name if sample.color else "NONE"
        if sample_color_name not in ALLOWED_COLORS:
            continue

        print(f"Sample color: {sample.color}")
        print(f"X: {sample.x}")
        print(f"Y: {sample.y}")

        # Apply filtering criteria
        if sample.y > MAX_REL_Y or sample.y < MIN_REL_Y:
            continue

        # Count neighbors
        number_of_neighbors = 0
        for other_sample in samples:
            if other_sample is None or other_sample is sample:
                continue

            dx = abs(sample.x - other_sample.x)
            dy = abs(sample.y - other_sample.y)

            if dx <= X_THRESHOLD and dy <= Y_THRESHOLD:
                number_of_neighbors += 1

        # Calculate coefficient (lower is better)
        coef = 2 * abs(sample.x) + abs(sample.y)
        coef += NEIGHBOR_PENALTY * number_of_neighbors

        # Update best sample if this one is better
        if coef < best_coef or (coef == best_coef and sample.color == SampleColor.YELLOW):
            best_sample = sample
            best_coef = coef

    return best_sample
