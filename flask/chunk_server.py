#!/usr/bin/python3
import xmlrpc.client
import time
import threading
import logging
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("chunk_server.log"), logging.StreamHandler()],
)
logger = logging.getLogger("ChunkServer")


class ChunkServer:
    def __init__(self, server_id, master_url):
        self.server_id = server_id
        self.master_url = master_url

        self.master = xmlrpc.client.ServerProxy(master_url)

        self.stored_chunks = set()
        self.running = False
        logger.info(f"Chunk Server {server_id} initialized")

    def start_heartbeat(self):
        """Start periodic heartbeat to master"""
        self.running = True

        def heartbeat_loop():
            while self.running:
                try:
                    server_info = {
                        "load": random.uniform(0.1, 0.8),
                        "storage_used_gb": random.uniform(10, 100),
                        "chunk_count": len(self.stored_chunks),
                        "version": "1.0",
                    }

                    response = self.master.heartbeat(self.server_id, server_info)
                    logger.debug(f"Heartbeat acknowledged: {response}")

                except Exception as e:
                    logger.error(f"Heartbeat failed: {e}")

                time.sleep(30)  # Heartbeat every 30 seconds

        threading.Thread(target=heartbeat_loop, daemon=True).start()
        logger.info("Heartbeat loop started")

    def stop(self):
        self.running = False


if __name__ == "__main__":
    # Create multiple chunk servers for demo
    servers = []
    for i in range(3):
        server = ChunkServer(f"chunk_server_{i}", "http://localhost:8000")
        server.start_heartbeat()
        servers.append(server)
        logger.info(f"Started chunk server {i}")

    try:
        # Keep servers running
        logger.info("All chunk servers running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down chunk servers...")
        for server in servers:
            server.stop()
        logger.info("All chunk servers stopped")
