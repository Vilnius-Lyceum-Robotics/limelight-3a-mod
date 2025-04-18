import math
from typing import Tuple


class RayProcessor:
    """
    A simplified processor for calculating world coordinates by ray-ground intersection.
    This handles a single camera tilt angle.
    """

    def __init__(self, fx: float, fy: float, cx: float, cy: float,
                 cam_x: float, cam_y: float, cam_z: float, tilt_angle_degrees: float):
        """
        Constructor for the position calculator

        Args:
            fx: Focal length in x direction (pixels)
            fy: Focal length in y direction (pixels)
            cx: Principal point x-coordinate (pixels)
            cy: Principal point y-coordinate (pixels)
            cam_x: Camera X position (inches)
            cam_y: Camera Y position (inches)
            cam_z: Camera Z position (inches)
            tilt_angle_degrees: Camera tilt angle in degrees (positive = tilted down)
        """
        self.fx = fx
        self.fy = fy
        self.cx = cx
        self.cy = cy
        self.cam_x = cam_x
        self.cam_y = cam_y
        self.cam_z = cam_z
        self.tilt_angle = math.radians(tilt_angle_degrees)
        self.cos_theta = math.cos(self.tilt_angle)
        self.sin_theta = math.sin(self.tilt_angle)

    def calculate_world_coordinates(self, pixel_x: float, pixel_y: float, object_z: float) -> Tuple[float, float]:
        """
        Calculate world X,Y coordinates for an object at a given pixel position and known Z height

        Args:
            pixel_x: X-coordinate in the image
            pixel_y: Y-coordinate in the image
            object_z: Z-coordinate in world space (inches from ground)

        Returns:
            Tuple containing (world_x, world_y) coordinates in inches
        """
        # Step 1: Convert pixel coordinates to normalized image coordinates
        normalized_x = (pixel_x - self.cx) / self.fx
        normalized_y = (pixel_y - self.cy) / self.fy

        # Step 2: Get ray direction in camera coordinates
        # In camera coordinates, the ray direction is [normalized_x, normalized_y, 1]
        ray_dir_x = normalized_x
        ray_dir_y = normalized_y
        ray_dir_z = 1.0

        # Step 3: Transform ray direction to world coordinates
        # Rotation matrix for camera tilted down around X-axis
        world_dir_x = ray_dir_x
        world_dir_y = self.cos_theta * ray_dir_y + self.sin_theta * ray_dir_z
        world_dir_z = -self.sin_theta * ray_dir_y + self.cos_theta * ray_dir_z

        # Step 4: Find intersection with Z = object_z plane
        # We need to find λ where: object_z = cam_z + λ * world_dir_z
        lambda_val = (object_z - self.cam_z) / world_dir_z

        # Step 5: Calculate world X and Y coordinates
        world_x = self.cam_x + lambda_val * world_dir_x
        world_y = self.cam_y + lambda_val * world_dir_y

        return world_x, world_y
