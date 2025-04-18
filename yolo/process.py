import threading
import time
import json
import subprocess
import sys
import math
from http.server import SimpleHTTPRequestHandler, HTTPServer
from typing import List, Dict, Optional, Any, Tuple

from urllib.parse import parse_qs, urlparse

from ultralytics import YOLO
from VideoStreamProcessor import VideoStreamProcessor
from RayProcessor import RayProcessor
from BestSampleDeterminer import Alliance, Sample, determine_best_sample
from LineAngleDetector import LineAngleDetector

# Configuration
STREAM_URL = "http://localhost:5802"
MODEL_PATH = "/home/pi/best_openvino_model/"
DETECTION_OUTPUT_PATH = "/dev/shm/detection_boxes.json"
TEST_IMAGE_PATH = "/home/pi/junk/testimg.jpg"
MODEL_IMAGE_SIZE = 320
MAX_STREAM_RETRIES = 3
VISION_SERVER_RESTART_WAIT = 20  # seconds

# Default allowed colors (all colors)
ALLOWED_COLORS = ['BLUE', 'YELLOW', 'RED']

# Camera parameters for RayProcessor
CAM_FX = 599.718  # focal length x
CAM_FY = 599.718  # focal length y
CAM_CX = 304.177  # principal point x
CAM_CY = 242.588  # principal point y
CAM_X = 0  # camera position x
CAM_Y = 2.76 / 25.4  # camera position y
CAM_Z = 406.175 / 25.4  # camera height
CAM_TILT = 142  # camera tilt angle

# Game-specific configuration
CURRENT_ALLIANCE = Alliance.BLUE  # Can be changed to Alliance.RED
ROBOT_X_COORD = 60.0  # Set this to your robot's x coordinate


def start_http_server(port=8000):
    """Start HTTP server in a separate thread"""
    log(f"Starting HTTP server on port {port}")
    server = HTTPServer(('0.0.0.0', port), DetectionHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server


class DetectionHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler for serving detection data and handling configuration"""

    def __init__(self, *args, **kwargs):
        # Set the directory to serve files from
        self.directory = "/dev/shm"
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # Suppress verbose logging
        pass

    def do_GET(self):
        # Parse URL path
        parsed_path = urlparse(self.path)

        # Handle color configuration endpoint
        if parsed_path.path == '/set_colors':
            query = parse_qs(parsed_path.query)
            colors = query.get('colors', [''])[0].upper().split(',')

            valid_colors = ['RED', 'BLUE', 'YELLOW']
            selected_colors = [c for c in colors if c in valid_colors]

            if selected_colors:
                # Update the global allowed colors
                global ALLOWED_COLORS
                ALLOWED_COLORS = selected_colors

                # Send response
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'success': True, 'colors': selected_colors}
                self.wfile.write(json.dumps(response).encode())
                log(f"Updated allowed colors to: {ALLOWED_COLORS}")
            else:
                # Send error response for invalid colors
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'success': False, 'error': 'No valid colors specified'}
                self.wfile.write(json.dumps(response).encode())
        elif parsed_path.path == "/detection_boxes.json":
            self.handle_detection_boxes()
        else:
            # Default behavior for serving files
            super().do_GET()

    def handle_detection_boxes(self):
        """
        Handle requests to /detection_boxes.json
        Loads and returns a JSON file containing detection boxes.
        """
        try:
            # Load detections (assume they are saved as JSON in the given directory)
            detection_file_path = DETECTION_OUTPUT_PATH

            with open(detection_file_path, 'r') as file:
                data = json.load(file)

            # Respond with the detection data
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=4).encode('utf-8'))
        except FileNotFoundError:
            # Handle if the file doesn't exist
            self.send_error(404, "Detection file not found")
        except Exception as e:
            # Handle other errors
            self.send_error(500, f"Error processing request: {str(e)}")


class Detection:
    """Class to hold detection data including original box coordinates and calculated world coordinates"""

    def __init__(self, class_id: int, x1: int, y1: int, x2: int, y2: int):
        """Initialize detection with bounding box coordinates"""
        self.class_id = class_id
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.world_x = None
        self.world_y = None

    def calculate_world_coordinates(self, ray_processor: RayProcessor, object_z: float = 0.0) -> None:
        """Calculate world coordinates for the center of the detection box"""
        center_x = (self.x1 + self.x2) / 2
        center_y = (self.y1 + self.y2) / 2

        self.world_x, self.world_y = ray_processor.calculate_world_coordinates(
            center_x, center_y, object_z
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert detection to dictionary for JSON serialization"""
        return {
            "class": self.class_id,
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "world_x": self.world_x,
            "world_y": self.world_y
        }

    def to_sample(self) -> Sample:
        """Convert detection to a Sample for best sample determination"""
        return Sample(self.class_id, self.world_x, self.world_y, self)


def log(msg: str) -> None:
    """Log a message to console and write status to the detection file."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
    with open(DETECTION_OUTPUT_PATH, "w+") as f:
        f.write(json.dumps({"index": -1, "status": msg, "detections": []}))


def restart_vision_server() -> None:
    """Restart the Limelight vision server service."""
    try:
        log("Restarting Limelight vision server...")
        subprocess.run(["sudo", "systemctl", "restart", "limelight_visionserver"], check=True)
        log(f"Vision server restart initiated. Waiting {VISION_SERVER_RESTART_WAIT}s...")
        time.sleep(VISION_SERVER_RESTART_WAIT)
    except subprocess.SubprocessError as e:
        log(f"Failed to restart vision server: {str(e)}")


def initialize_model() -> YOLO:
    """Initialize and warm up the YOLO model."""
    log("Initializing model...")
    model = YOLO(MODEL_PATH)
    log("Model loaded successfully")

    # Warm up the model
    log("Warming up model...")
    model(TEST_IMAGE_PATH, imgsz=MODEL_IMAGE_SIZE)
    log("Model warmup complete")

    return model


def initialize_ray_processor() -> RayProcessor:
    """Initialize the ray processor for 3D coordinate calculations."""
    log("Initializing ray processor...")
    ray_processor = RayProcessor(
        fx=CAM_FX,
        fy=CAM_FY,
        cx=CAM_CX,
        cy=CAM_CY,
        cam_x=CAM_X,
        cam_y=CAM_Y,
        cam_z=CAM_Z,
        tilt_angle_degrees=CAM_TILT
    )
    log("Ray processor initialized")
    return ray_processor


def initialize_line_angle_detector() -> LineAngleDetector:
    """Initialize the line angle detector."""
    log("Initializing line angle detector...")
    line_angle_detector = LineAngleDetector()
    log("Line angle detector initialized")
    return line_angle_detector


def connect_to_stream() -> Optional[VideoStreamProcessor]:
    """Attempt to connect to the video stream with retries."""
    for attempt in range(1, MAX_STREAM_RETRIES + 1):
        log(f"Starting stream thread... Attempt {attempt}/{MAX_STREAM_RETRIES}")

        stream = VideoStreamProcessor(STREAM_URL)
        if stream.start():
            log("Stream started successfully")
            return stream

        if attempt < MAX_STREAM_RETRIES:
            restart_vision_server()

    log(f"Failed to start stream after {MAX_STREAM_RETRIES} attempts")
    return None


def process_detections(results: Any, ray_processor: RayProcessor) -> List[Detection]:
    """Extract detection information from model results and calculate world coordinates."""
    detections = []

    for r in results:
        boxes = r.boxes.xyxy
        classes = r.boxes.cls
        for i in range(len(boxes)):
            detection = Detection(
                class_id=int(classes[i]),
                x1=int(boxes[i][0]),
                y1=int(boxes[i][1]),
                x2=int(boxes[i][2]),
                y2=int(boxes[i][3])
            )

            detection.calculate_world_coordinates(ray_processor)
            detections.append(detection)

    return detections


def save_detections(frame_index: int, detections: List[Detection], best_sample) -> None:
    """Save detection results and best sample to shared memory."""
    detection_dicts = [detection.to_dict() for detection in detections]

    result = {
        "index": frame_index,
        "status": "OK",
        "detections": detection_dicts,
    }

    # Add best sample if found
    if best_sample is not None:
        result["best_sample"] = best_sample

    with open(DETECTION_OUTPUT_PATH, "w+") as db:
        db.write(json.dumps(result))


def process_frames(model: YOLO, stream: VideoStreamProcessor, ray_processor: RayProcessor,
                   line_angle_detector: LineAngleDetector) -> None:
    """Process video frames continuously."""
    global ALLOWED_COLORS
    frame_index = 0
    dead_frame_count = 0

    while True:
        try:
            # Get frame from stream
            image = stream.read()
            if image is None:
                dead_frame_count += 1
                if dead_frame_count > 50:
                    connect_to_stream()
                time.sleep(0.1)
                continue

            dead_frame_count = 0

            # Run model inference
            results = model(image.copy(), imgsz=MODEL_IMAGE_SIZE)

            # Process detections and calculate world coordinates
            detections = process_detections(results, ray_processor)

            # Convert detections to samples for best sample determination
            samples = [detection.to_sample() for detection in detections]

            # Determine best sample
            best_sample = determine_best_sample(samples, ALLOWED_COLORS, ROBOT_X_COORD)
            if best_sample:
                angle = line_angle_detector.detect_line(image, best_sample.detection)
                # angle = 0
                real_angle = -180

                if angle["success"]:
                    # zalibal
                    # Determine real angle
                    p1, p2 = angle["endpoints"]
                    real_p1 = ray_processor.calculate_world_coordinates(p1[0], p1[1], 1.5)
                    real_p2 = ray_processor.calculate_world_coordinates(p2[0], p2[1], 1.5)
                    real_angle = math.atan2(real_p2[1] - real_p1[1], real_p2[0] - real_p1[0])

                best_sample = {
                    "color": best_sample.color.name if best_sample.color else "NONE",
                    "x": best_sample.x,
                    "y": best_sample.y,
                    "angle": real_angle
                }

            # Save enhanced detections and best sample
            save_detections(frame_index, detections, best_sample)
            frame_index += 1

        except Exception as e:
            log(f"Error processing frame: {str(e)}")
            time.sleep(0.1)  # Prevent tight loop on repeated errors


def main() -> int:
    """Main program entry point."""
    try:
        # Start the integrated HTTP server
        http_server = start_http_server()
        # Initialize model
        model = initialize_model()

        # Initialize ray processor
        ray_processor = initialize_ray_processor()
        #
        line_angle_detector = initialize_line_angle_detector()

        # Connect to stream
        stream = connect_to_stream()
        if stream is None:
            return 1

        # Process frames continuously
        process_frames(model, stream, ray_processor, line_angle_detector)

    except KeyboardInterrupt:
        log("Program terminated by user")
        return 0
    except Exception as e:
        log(f"Unhandled exception: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
