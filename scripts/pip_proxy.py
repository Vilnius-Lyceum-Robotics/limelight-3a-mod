import http.server
import socketserver
import urllib.request
import urllib.error
import re
from urllib.parse import urlparse, parse_qs, unquote
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
HOST = "0.0.0.0"  # Listen on all interfaces
PORT = 8000
PYPI_URL = "https://pypi.org"
PYPI_FILES_URL = "https://files.pythonhosted.org"

class PyPIProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            logger.info(f"Received request: {self.path}")
            
            # Parse the path
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query = parsed_path.query
            
            # Determine if we're handling a PyPI or files.pythonhosted.org request
            if path.startswith("/simple/"):
                # This is a PyPI package listing request
                target_url = f"{PYPI_URL}{path}"
                if query:
                    target_url += f"?{query}"
                
                logger.info(f"Forwarding to PyPI: {target_url}")
                response = urllib.request.urlopen(target_url)
                content = response.read().decode('utf-8')
                
                # Replace HTTPS URLs with HTTP URLs through our proxy
                # Replace links to files.pythonhosted.org
                content = content.replace(
                    'href="https://files.pythonhosted.org', 
                    f'href="http://{self.headers["Host"]}/files'
                )
                
                # Replace links back to PyPI
                content = content.replace(
                    'href="https://pypi.org', 
                    f'href="http://{self.headers["Host"]}'
                )
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                
            elif path.startswith("/files/"):
                # This is a files.pythonhosted.org request
                # Strip the /files prefix from path but keep the leading slash
                file_path = path[6:]  # Remove /files prefix (not /files/)
                
                # Make sure file_path starts with a slash
                if not file_path.startswith('/'):
                    file_path = '/' + file_path
                
                target_url = f"{PYPI_FILES_URL}{file_path}"
                if query:
                    target_url += f"?{query}"
                
                logger.info(f"Forwarding to files.pythonhosted.org: {target_url}")
                response = urllib.request.urlopen(target_url)
                
                # Forward the response headers
                self.send_response(response.status)
                for header, value in response.getheaders():
                    if header.lower() not in ('transfer-encoding', 'content-length'):
                        self.send_header(header, value)
                self.end_headers()
                
                # Stream the file content to avoid memory issues with large files
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                
            elif path.startswith("/pypi/"):
                # Handle PyPI JSON API requests
                api_path = path[5:]  # Remove /pypi/ prefix
                target_url = f"{PYPI_URL}/pypi/{api_path}"
                if query:
                    target_url += f"?{query}"
                
                logger.info(f"Forwarding to PyPI API: {target_url}")
                response = urllib.request.urlopen(target_url)
                content = response.read()
                
                self.send_response(200)
                for header, value in response.getheaders():
                    if header.lower() not in ('transfer-encoding', 'content-length'):
                        self.send_header(header, value)
                self.end_headers()
                self.wfile.write(content)
            
            else:
                # Forward other PyPI requests
                target_url = f"{PYPI_URL}{path}"
                if query:
                    target_url += f"?{query}"
                
                logger.info(f"Forwarding to PyPI: {target_url}")
                response = urllib.request.urlopen(target_url)
                content = response.read()
                
                self.send_response(200)
                for header, value in response.getheaders():
                    if header.lower() not in ('transfer-encoding', 'content-length'):
                        self.send_header(header, value)
                self.end_headers()
                self.wfile.write(content)
                
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP error: {e.code} - {e.reason}")
            self.send_response(e.code)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Error: {e.code} - {e.reason}".encode())
        
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Internal server error: {str(e)}".encode())

def main():
    server = socketserver.TCPServer((HOST, PORT), PyPIProxyHandler)
    logger.info(f"Starting PyPI proxy server on http://{HOST}:{PORT}")
    logger.info(f"Configure pip on your CM4 with: pip install --index-url http://YOUR_PC_IP:{PORT}/simple/ your_package")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
