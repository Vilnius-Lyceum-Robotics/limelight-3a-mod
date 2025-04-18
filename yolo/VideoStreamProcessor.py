import socket
import numpy as np
import cv2
import time
import subprocess
import signal
import os
import atexit
from threading import Thread


class VideoStreamProcessor:
    def __init__(self, url=None, host='127.0.0.1', port=5000, width=640, height=480, start_gstreamer=True):
        """
        Initialize the VideoStreamProcessor
        
        Args:
            url: Optional legacy parameter (ignored, kept for compatibility)
            host: TCP server hostname/IP
            port: TCP server port
            width: Frame width
            height: Frame height
            start_gstreamer: Whether to start the GStreamer pipeline automatically
        """
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.bytes_per_pixel = 3
        self.bytes_per_frame = width * height * self.bytes_per_pixel

        self.last_frame_data = None
        self.freeze_counter = 0
        self.max_freeze_count = 10  # Max number of identical frames before restart
        self.frame_check_interval = 5  # Check every N frames
        self.frame_counter = 0

        self.current_frame = None
        self.stopped = False
        self.sock = None
        self.connected = False
        self.thread = None
        self.gst_process = None

        # Command template for GStreamer pipeline
        self.gst_command = (
            f"gst-launch-1.0 libcamerasrc ! video/x-raw,width={width},height={height} ! "
            f"videoconvert ! video/x-raw,format=I420 ! videoconvert ! video/x-raw,format=RGB ! "
            f"tcpserversink host={host} port={port} sync=false"
        )

        # Start GStreamer if requested
        if start_gstreamer:
            self.start_gstreamer_pipeline()

        # Register cleanup handler
        atexit.register(self.cleanup)

    def start_gstreamer_pipeline(self):
        """Start the GStreamer pipeline as a subprocess"""
        if self.gst_process is not None:
            # Ensure old process is terminated
            try:
                if self.gst_process.poll() is None:
                    print("GStreamer pipeline is already running")
                    return True
                else:
                    print("Previous GStreamer process has ended, cleaning up")
                    self.gst_process = None
            except:
                self.gst_process = None

        try:
            print(f"Starting GStreamer pipeline: {self.gst_command}")

            # Check if we need sudo (libcamerasrc often requires it)
            if os.geteuid() != 0:  # Not running as root
                cmd = ["sudo"] + self.gst_command.split()
                print("Running with sudo privileges")
            else:
                cmd = self.gst_command.split()

            # Start the process with a cleaner environment
            env = os.environ.copy()
            # Add GST_DEBUG=2 for basic debugging without overwhelming output
            env["GST_DEBUG"] = "2"

            # Start the process
            self.gst_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )

            # Give the pipeline a moment to start
            time.sleep(2)

            # Check if the process is still running
            if self.gst_process.poll() is None:
                print("GStreamer pipeline started successfully")
                return True
            else:
                # Process exited already, get error
                _, stderr = self.gst_process.communicate(timeout=1)
                print(f"GStreamer pipeline failed to start: {stderr}")
                self.gst_process = None
                return False

        except Exception as e:
            print(f"Failed to start GStreamer pipeline: {e}")
            if self.gst_process:
                try:
                    self.gst_process.terminate()
                except:
                    pass
                self.gst_process = None
            return False

    def start(self):
        """Start processing the video stream"""
        # Start the frame reading thread
        self.thread = Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()
        return True

    def _connect(self):
        """Establish connection to the TCP server"""
        try:
            # Create socket and connect
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))

            # Set socket options
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(5.0)

            self.connected = True
            print(f"Connected to camera stream at {self.host}:{self.port}")
            return True

        except ConnectionRefusedError:
            print(f"Connection refused to {self.host}:{self.port}. Is the GStreamer pipeline running?")
        except Exception as e:
            print(f"Connection error: {e}")

        self.connected = False
        return False

    def update(self):
        """Thread method to receive frames from TCP socket and update current_frame"""
        buffer = b''
        total_frames = 0
        start_time = time.time()

        while not self.stopped:
            # Attempt to connect if not connected
            if not self.connected:
                if self._connect():
                    buffer = b''  # Reset buffer after new connection
                else:
                    # Check if GStreamer process has crashed
                    if self.gst_process and self.gst_process.poll() is not None:
                        print("GStreamer process has crashed, restarting...")
                        self.start_gstreamer_pipeline()
                        time.sleep(2)  # Wait for pipeline to start

                    # Retry after delay
                    time.sleep(5)
                    continue

            try:
                # Receive data
                data = self.sock.recv(self.bytes_per_frame)
                if not data:
                    print("Connection closed by server")
                    self.connected = False
                    continue

                # Add to buffer
                buffer += data

                # Process complete frames
                while len(buffer) >= self.bytes_per_frame:
                    # Extract one complete frame
                    frame_data = buffer[:self.bytes_per_frame]
                    buffer = buffer[self.bytes_per_frame:]

                    # Process the frame
                    frame = np.frombuffer(frame_data, dtype=np.uint8).reshape((self.height, self.width, 3))

                    # Check for frozen frames
                    self.frame_counter += 1
                    if self.frame_counter % self.frame_check_interval == 0:
                        self._check_for_frozen_frame(frame_data)

                    # Convert RGB to BGR for OpenCV
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                    # Update current_frame
                    self.current_frame = frame_bgr
                    total_frames += 1

                    # Status report periodically
                    if total_frames % 150 == 0:
                        elapsed = time.time() - start_time
                        fps = total_frames / elapsed if elapsed > 0 else 0
                        print(f"Stream rate: {fps:.1f} fps, Frames processed: {total_frames}")

            except socket.timeout:
                print("Socket timeout - reconnecting")
                self.connected = False
            except Exception as e:
                print(f"Error in update thread: {e}")
                self.connected = False
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass

    def read(self):
        """Return the current frame"""
        return self.current_frame

    def stop(self):
        """Stop the stream processing and GStreamer pipeline"""
        self.stopped = True

        # Close the socket
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

        # Stop the GStreamer pipeline
        self.stop_gstreamer_pipeline()

        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join()

    def _check_for_frozen_frame(self, frame_data):
        """Check if the current frame is identical to previous frames"""
        if self.last_frame_data is not None and np.array_equal(frame_data, self.last_frame_data):
            self.freeze_counter += 1
            print(f"Potential frame freeze detected ({self.freeze_counter}/{self.max_freeze_count})")

            if self.freeze_counter >= self.max_freeze_count:
                print("Stream appears to be frozen, restarting GStreamer pipeline")
                # Force reconnection and restart GStreamer
                self.connected = False
                self.stop_gstreamer_pipeline()
                time.sleep(1)
                self.start_gstreamer_pipeline()
                time.sleep(2)
                self.freeze_counter = 0
        else:
            self.freeze_counter = 0

        # Update last frame data - use a new bytes object instead of copy()
        self.last_frame_data = bytes(frame_data)

    def stop_gstreamer_pipeline(self):
        """Stop the GStreamer pipeline subprocess"""
        if self.gst_process and self.gst_process.poll() is None:
            print("Stopping GStreamer pipeline...")
            try:
                # Try to terminate gracefully
                self.gst_process.terminate()
                self.gst_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # Force kill if needed
                print("Forcing GStreamer pipeline to stop")
                self.gst_process.kill()
            finally:
                self.gst_process = None

    def cleanup(self):
        """Cleanup method for atexit handler"""
        self.stop()
