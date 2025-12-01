#!/usr/bin/python3
from xmlrpc.server import SimpleXMLRPCServer
import logging
import time
import threading
from collections import defaultdict
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("master_server.log"), logging.StreamHandler()],
)
logger = logging.getLogger("MasterServer")


class MasterServer:
    def __init__(self, host="localhost", port=8000):
        self.server = SimpleXMLRPCServer(
            (host, port), logRequests=False, allow_none=True
        )

        # System state
        self.chunk_servers = {}  # server_id -> last_heartbeat, chunks, metadata
        self.videos = {}  # video_id -> video metadata
        self.uploads_today = 0
        self.last_reset = time.time()

        self.setup_methods()
        logger.info(f"Master Server initialized on {host}:{port}")

    def setup_methods(self):
        """Register all RPC methods"""
        self.server.register_function(self.ping)
        self.server.register_function(self.heartbeat)
        self.server.register_function(self.register_video)
        self.server.register_function(self.get_system_status)
        self.server.register_function(self.get_chunk_servers)
        self.server.register_function(self.register_chunk)

    def ping(self):
        """Simple health check"""
        return "pong"

    def heartbeat(self, server_id, server_info):
        """Process heartbeat from chunk servers"""
        current_time = time.time()
        self.chunk_servers[server_id] = {
            "last_heartbeat": current_time,
            "info": server_info,
            "status": "healthy",
        }

        logger.info(f"Heartbeat from {server_id} - Load: {server_info.get('load', 0)}")
        return {"status": "ack", "timestamp": current_time}

    def register_video(self, video_data):
        """Register a new video in the system"""
        video_id = video_data["video_id"]
        self.videos[video_id] = video_data
        self.uploads_today += 1

        logger.info(
            f"Video registered - ID: {video_id}, Title: {video_data['title']}, Chunks: {video_data['chunk_count']}"
        )

        return {"status": "registered", "video_id": video_id}

    def get_system_status(self):
        """Return current system status for admin console"""
        # Reset daily counter if needed
        if time.time() - self.last_reset > 86400:  # 24 hours
            self.uploads_today = 0
            self.last_reset = time.time()

        active_servers = sum(
            1
            for s in self.chunk_servers.values()
            if time.time() - s["last_heartbeat"] < 60
        )  # 60 second timeout

        total_storage_gb = sum(v["total_size"] for v in self.videos.values()) / (
            1024**3
        )

        return {
            "connected": True,
            "active_servers": active_servers,
            "total_videos": len(self.videos),
            "uploads_today": self.uploads_today,
            "total_storage": f"{total_storage_gb:.2f} GB",
            "health": "healthy" if active_servers > 0 else "degraded",
            "timestamp": time.time(),
        }

    def get_chunk_servers(self):
        """Return list of active chunk servers"""
        active_servers = []
        current_time = time.time()

        for server_id, server_data in self.chunk_servers.items():
            if current_time - server_data["last_heartbeat"] < 60:  # 60 second timeout
                active_servers.append(
                    {
                        "id": server_id,
                        "status": server_data["status"],
                        "last_seen": server_data["last_heartbeat"],
                        "info": server_data["info"],
                    }
                )

        return active_servers

    def register_chunk(self, chunk_id, server_id, video_id):
        """Register a chunk with a specific server"""
        logger.debug(
            f"Chunk registered - Chunk: {chunk_id}, Server: {server_id}, Video: {video_id}"
        )
        return True

    def serve_forever(self):
        """Start the server"""
        logger.info("Starting XML-RPC master server...")
        self.server.serve_forever()


if __name__ == "__main__":
    server = MasterServer()
    server.serve_forever()
