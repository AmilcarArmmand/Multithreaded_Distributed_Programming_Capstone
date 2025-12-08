#!/usr/bin/python3
from flask import Flask, request, jsonify, render_template_string
from xmlrpc.client import ServerProxy
import time
from loguru import logger
import os
from werkzeug.utils import secure_filename
import threading
import uuid

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024 * 1024  # 16GB max upload

# Configuration
MASTER_SERVER_URL = "http://localhost:8000"
UPLOAD_FOLDER = "./uploads"
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}


class MasterClient:
    def __init__(self):
        self.master = ServerProxy(MASTER_SERVER_URL)
        self.connected = False
        self.test_connection()
        self.leader_election_proxy = ServerProxy("http://localhost:9000")

    def test_connection(self):
        try:
            self.master.ping()
            self.connected = True
            logger.info("Connected to master server")
        except Exception as e:
            logger.error(f"Failed to connect to master: {e}")
            self.connected = False

    def register_upload(self, video_data, job_id):
        if not self.connected:
            raise ConnectionError("Not connected to master server")
        return self.master.register_video(video_data, job_id)

    def get_system_status(self):
        if not self.connected:
            return {"error": "Not connected to master"}
        return self.master.get_system_status()

    def get_chunk_servers(self, job_id):
        if not self.connected:
            return []
        return self.master.get_chunk_servers(job_id)


# Global master client
master_client = MasterClient()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def chunk_file(file_path, chunk_size=10 * 1024 * 1024):  # 10MB chunks
    chunks = []
    chunk_id = 0

    with open(file_path, "rb") as f:
        while True:
            chunk_data = f.read(chunk_size)
            if not chunk_data:
                break

            chunk_info = {
                "chunk_id": f"{os.path.basename(file_path)}_{chunk_id}",
                "data": chunk_data,
                "size": len(chunk_data),
                "sequence": chunk_id,
            }
            chunks.append(chunk_info)
            chunk_id += 1

    return chunks


def upload_chunk_to_server(chunk_info, chunk_server, job_id):
    try:
        time.sleep(1)  # Simulate upload time
        logger.info(f"Uploaded chunk {chunk_info['chunk_id']} to {chunk_server}")
        server_proxy = ServerProxy(f"http://localhost:{8005 + int(chunk_server['id'].split('_')[-1])}")
        server_proxy.store_chunk(chunk_info["chunk_id"], chunk_info["data"], job_id)
        return True
    except Exception as e:
        logger.error(f"Failed to upload chunk {chunk_info['chunk_id']}: {e}")
        return False


# Flask Routes
@app.route("/")
def dashboard():
    try:
        system_status = master_client.get_system_status()
    except Exception as e:
        system_status = {"error": str(e)}
        chunk_servers = []

    return render_template_string(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Video Streaming Service - Admin Console</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .card { border: 1px solid #ddd; padding: 20px; margin: 10px 0; border-radius: 5px; }
                .success { background-color: #d4edda; }
                .warning { background-color: #fff3cd; }
                .error { background-color: #f8d7da; }
                .upload-form { margin: 20px 0; }
                .status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
            </style>
        </head>
        <body>
            <h1>Video Streaming Service - Admin Console</h1>

            <div class="status-grid">
                <div class="card {{ 'success' if system_status.connected else 'error' }}">
                    <h3>Master Server Status</h3>
                    <p>Connected: {{ system_status.connected }}</p>
                    <p>Active Servers: {{ system_status.active_servers or 0 }}</p>
                    <p>Total Videos: {{ system_status.total_videos or 0 }}</p>
                </div>

                <div class="card">
                    <h3>Chunk Servers</h3>
                    <ul>
                        {% for server in chunk_servers %}
                            <li>{{ server.id }} - {{ server.status }}</li>
                        {% endfor %}
                    </ul>
                </div>
            </div>

            <div class="upload-form">
                <h3>Upload Video</h3>
                <form action="/upload" method="post" enctype="multipart/form-data">
                    <input type="file" name="video" accept="video/*" required>
                    <input type="text" name="title" placeholder="Video Title" required>
                    <textarea name="description" placeholder="Description"></textarea>
                    <button type="submit">Upload Video</button>
                </form>
            </div>

            <div class="card">
                <h3>System Metrics</h3>
                <button onclick="refreshMetrics()">Refresh Metrics</button>
                <div id="metrics"></div>
            </div>

            <script>
                function refreshMetrics() {
                    fetch('/api/metrics')
                        .then(r => r.json())
                        .then(data => {
                            document.getElementById('metrics').innerHTML =
                                'Uploads Today: ' + data.uploads_today + '<br>' +
                                'Total Storage: ' + data.total_storage + '<br>' +
                                'System Health: ' + data.health;
                        });
                }
            </script>
        </body>
        </html>
    """,
        system_status=system_status,
        chunk_servers=chunk_servers,
    )


@app.route("/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file"}), 400

    file = request.files["video"]
    title = request.form.get("title", "Untitled")

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(file_path)

            threading.Thread(
                target=process_video_upload,
                args=(file_path, title, request.form.get("description")),
            ).start()

            return (
                jsonify(
                    {
                        "message": "Video upload started",
                        "filename": filename,
                        "title": title,
                    }
                ),
                202,
            )

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Invalid file type"}), 400


def process_video_upload(file_path, title, description):
    try:
        job_id = str(uuid.uuid4())
        logger.info(f"Processing video upload: {title}")

        chunks = chunk_file(file_path)
        logger.info(f"Split into {len(chunks)} chunks")

        retries = 0
        for chunk in chunks:
            print("uploading chunk", chunk["chunk_id"])
            
            while retries < 3:
                try: 
                    chunk_servers = master_client.get_chunk_servers(job_id)
                    upload_chunk_to_server(chunk, chunk_servers, job_id)
                    break
                except Exception as e:
                    logger.error(f"Video processing failed: {e}")
                    retries += 1
                    if retries == 3:
                        proxy = ServerProxy("http://localhost:9000")
                        new_leader = proxy.current_leader() 
                        if new_leader == master_client.master._ServerProxy__host:
                            time.sleep(2)
                        master_client.master = ServerProxy(new_leader)
                        logger.info(f"Switched to new master at {new_leader}")
                        retries = 0
                        

        video_data = {
            "video_id": f"vid_{int(time.time())}",
            "title": title,
            "description": description,
            "filename": os.path.basename(file_path),
            "chunk_count": len(chunks),
            "total_size": sum(chunk["size"] for chunk in chunks),
            "upload_time": time.time(),
        }

        master_client.register_upload(video_data, job_id)
        logger.info(f"Successfully uploaded video: {title}")

        os.remove(file_path)

    except Exception as e:
        logger.error(f"Video processing failed: {e}")
        new_leader = master_client.leader_election_proxy.current_leader() 
        master_client.master = ServerProxy(new_leader)
        logger.info(f"Switched to new master at {new_leader}")
        return False



@app.route("/api/metrics")
def get_metrics():
    try:
        system_status = master_client.get_system_status()
        return jsonify(
            {
                "uploads_today": system_status.get("uploads_today", 0),
                "total_storage": system_status.get("total_storage", "0 GB"),
                "health": system_status.get("health", "unknown"),
                "active_servers": system_status.get("active_servers", 0),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# @app.route("/api/servers")
# def get_servers():
#     try:
#         servers = master_client.get_chunk_servers()
#         return jsonify(servers)
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.add("flask_app.log", serialize=True, rotation="10 MB")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(host="0.0.0.0", port=5001, debug=True)
