import cv2
import numpy as np
import math
from typing import Optional, Tuple, Dict, Any


class LineAngleDetector:
    """
    Detects the longest line in an object and calculates its angle.
    Processes a single frame without any filtering.
    """

    # Color definitions for segmentation (HSV ranges)
    COLOR_RANGES = {
        0: {  # Blue (class_id = 0)
            'name': 'blue',
            'ranges': {
                'lower': np.array([90, 70, 50]),
                'upper': np.array([140, 255, 255])
            }
        },
        1: {  # Red (class_id = 1)
            'name': 'red',
            'ranges': {
                'lower1': np.array([0, 70, 50]),
                'upper1': np.array([10, 255, 255]),
                'lower2': np.array([160, 70, 50]),
                'upper2': np.array([180, 255, 255])
            }
        },
        2: {  # Yellow (class_id = 2)
            'name': 'yellow',
            'ranges': {
                'lower': np.array([15, 70, 50]),
                'upper': np.array([45, 255, 255])
            }
        }
    }

    def __init__(self):
        """Initialize the line angle detector."""
        # Configuration parameters
        self.min_line_length = 15  # Minimum line length to consider
        self.max_line_gap = 10  # Maximum gap between line segments
        self.hough_threshold = 15  # Minimum number of intersections for Hough
        self.border_margin = 2  # Margin to ignore border lines
        self.angle_threshold = 10  # Angle threshold for grouping lines
        self.distance_threshold = 20  # Distance threshold for grouping lines

    def is_on_border(self, point: Tuple[int, int], width: int, height: int) -> bool:
        """Check if a point is on the border of the image."""
        x, y = point
        return (x <= self.border_margin or x >= width - self.border_margin or
                y <= self.border_margin or y >= height - self.border_margin)

    def detect_line(self, image: np.ndarray, detection: Any) -> Dict[str, Any]:
        """
        Detect the longest line in the detection area and calculate its angle.

        Args:
            image: Full frame image (BGR format)
            detection: Detection object with class_id, x1, y1, x2, y2 attributes

        Returns:
            Dictionary with detection results including:
                - success: Whether a line was successfully detected
                - angle_degrees: Angle of the line in degrees (if success)
                - endpoints: Line endpoints ((x1,y1), (x2,y2)) (if success)
                - angle_radians: Angle in radians (if success)
        """
        # Extract detection information
        class_id = detection.class_id
        x1, y1, x2, y2 = detection.x1-8, detection.y1-8, detection.x2+8, detection.y2+8

        # Create a default result with failure status
        result = {
            'success': False,
            'angle_degrees': None,
            'angle_radians': None,
            'endpoints': None
        }

        # Check if class_id is valid
        if class_id not in self.COLOR_RANGES:
            return result

        # Extract the region of interest
        roi = image[y1:y2, x1:x2]
        if roi.size == 0:  # Check if ROI is valid
            return result

        # Get ROI dimensions
        roi_height, roi_width = roi.shape[:2]

        # Convert ROI to HSV for color segmentation
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Get color segmentation mask
        color_data = self.COLOR_RANGES[class_id]

        if class_id == 1:  # Red (requires two ranges due to hue wraparound)
            mask1 = cv2.inRange(hsv, color_data['ranges']['lower1'], color_data['ranges']['upper1'])
            mask2 = cv2.inRange(hsv, color_data['ranges']['lower2'], color_data['ranges']['upper2'])
            color_mask = cv2.bitwise_or(mask1, mask2)
        else:  # Blue or Yellow
            color_mask = cv2.inRange(hsv, color_data['ranges']['lower'], color_data['ranges']['upper'])

        # Refine the mask
        kernel = np.ones((5, 5), np.uint8)
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel)  # Remove noise
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel)  # Fill gaps

        # Find contours
        contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Check if we found any contours
        if not contours:
            return result

        # Find the largest contour
        main_contour = max(contours, key=cv2.contourArea)

        # Create a mask for just the main contour
        object_mask = np.zeros((roi_height, roi_width), dtype=np.uint8)
        cv2.drawContours(object_mask, [main_contour], 0, 255, -1)

        # Get the edge points using Canny
        edges = cv2.Canny(object_mask, 100, 200)

        # Use Hough Line Transform to detect straight lines
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180,
                                threshold=self.hough_threshold,
                                minLineLength=self.min_line_length,
                                maxLineGap=self.max_line_gap)

        if lines is None or len(lines) == 0:
            return result

        # Process lines - group similar line segments
        line_groups = self._group_line_segments(lines, roi_width, roi_height)

        if not line_groups:
            return result

        # Find the line group with the longest total length
        longest_group = max(line_groups, key=lambda group: sum(line['length'] for line in group))

        # Find the two most distant points
        all_points = []
        for line in longest_group:
            x1, y1, x2, y2 = line['points']
            all_points.append((x1, y1))
            all_points.append((x2, y2))

        # If no points (shouldn't happen)
        if not all_points:
            return result

        # Find the two points with maximum distance
        max_distance = 0
        endpoints = None

        for i, point1 in enumerate(all_points):
            for point2 in all_points[i + 1:]:
                x1, y1 = point1
                x2, y2 = point2
                distance = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

                if distance > max_distance:
                    max_distance = distance
                    endpoints = ((int(x1), int(y1)), (int(x2), int(y2)))

        if not endpoints:
            return result

        # Adjust endpoints to be relative to the original image
        (lx1, ly1), (lx2, ly2) = endpoints
        global_endpoints = ((float(x1 + lx1), float(y1 + ly1)), (float(x1 + lx2), float(y1 + ly2)))

        # Calculate angle
        angle_rad = np.arctan2(ly2 - ly1, lx2 - lx1)
        angle_deg = np.degrees(angle_rad) % 180

        # Return successful result
        return {
            'success': True,
            'angle_degrees': float(angle_deg),
            'angle_radians': float(angle_rad),
            'endpoints': global_endpoints
        }

    def _group_line_segments(self, lines, width, height):
        """Group similar line segments based on angle and proximity."""
        groups = []
        used_indices = set()

        # Process lines
        processed_lines = []
        for i, line in enumerate(lines):
            x1, y1, x2, y2 = line[0]

            # Skip border lines
            if self.is_on_border((x1, y1), width, height) or self.is_on_border((x2, y2), width, height):
                continue

            length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180
            processed_lines.append({
                'index': i,
                'points': (x1, y1, x2, y2),
                'length': length,
                'angle': angle,
                'midpoint': ((x1 + x2) / 2, (y1 + y2) / 2)
            })

        # Sort by length
        processed_lines.sort(key=lambda x: x['length'], reverse=True)

        # Form groups
        for i, line1 in enumerate(processed_lines):
            if line1['index'] in used_indices:
                continue

            current_group = [line1]
            used_indices.add(line1['index'])

            # Find similar lines
            for line2 in processed_lines:
                if line2['index'] in used_indices:
                    continue

                # Check angle similarity
                angle_diff = min((line1['angle'] - line2['angle']) % 180,
                                 (line2['angle'] - line1['angle']) % 180)

                if angle_diff > self.angle_threshold:
                    continue

                # Check proximity
                mp1 = line1['midpoint']
                mp2 = line2['midpoint']
                distance = np.sqrt((mp1[0] - mp2[0]) ** 2 + (mp1[1] - mp2[1]) ** 2)

                if distance > self.distance_threshold:
                    continue

                # Add to group
                current_group.append(line2)
                used_indices.add(line2['index'])

            groups.append(current_group)

        return groups
