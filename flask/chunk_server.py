#!/usr/bin/python3
import os
from xmlrpc.client import ServerProxy
from xmlrpc.server import SimpleXMLRPCServer
import time
import threading
from loguru import logger
import random

class ChunkServer:
    def __init__(self, server_id, master_url):
        self.server_id = server_id
        self.master_url = master_url
        self.master = ServerProxy(master_url)
        self.election_proxy = ServerProxy("http://localhost:9000")
        self.chunk_server_url = f"http://localhost:{8005 + int(self.server_id.split('_')[-1])}"
        self.server = SimpleXMLRPCServer(
            ("localhost", 8005 + int(self.server_id.split('_')[-1])), logRequests=False, allow_none=True
        )

        self.stored_chunks = {}
        self.running = False
        logger.info(f"Chunk Server {server_id} initialized")
    
    def store_chunk(self, chunk_id, data, job_id):
        if hasattr(data, 'data'):
            data = data.data  # Unwrap Binary object
        self.stored_chunks[chunk_id] = data
        logger.info(f"Stored chunk {chunk_id}", chunk_id=chunk_id)
        os.makedirs(f"chunks/{self.server_id}", exist_ok=True)
        path = os.path.join(f"chunks/{self.server_id}", f"{chunk_id}_{job_id}.chk")
        with open(path, "wb") as f:
            f.write(data)
    
    def assemble_video(self, job_id):
        os.makedirs(f"videos/{self.server_id}", exist_ok=True)
        chunks = list(self.stored_chunks.keys())
        chunks.sort()
        video_data = b"".join(self.stored_chunks[chunk_id] for chunk_id in chunks)
        path = os.path.join(f"videos/{self.server_id}", f"{self.server_id}_video_{job_id}.mp4")
        with open(path, "wb") as f:
            f.write(video_data)
        logger.info(f"Video assembled and saved to {path}")
        return video_data

    def start_heartbeat(self):
        self.running = True

        def heartbeat_loop():
            number_of_failures = 0
            while self.running:
                try:
                    server_info = {
                        "load": random.uniform(0.1, 0.8),
                        "storage_used_gb": random.uniform(10, 100),
                        "chunk_count": len(self.stored_chunks),
                        "version": "1.0",
                    }
                    if number_of_failures < 3:
                        response = self.master.heartbeat(self.server_id, server_info)
                        logger.debug(f"Heartbeat acknowledged: {response}")
                        number_of_failures = 0

                except Exception as e:
                    logger.error(f"heartbeat error: {e}")
                    number_of_failures += 1
                    if number_of_failures == 3:
                        self.master_url = self.election_proxy.current_leader()
                        self.master = ServerProxy(self.master_url)
                        logger.info(f"Switched to new master at {self.master_url}")
                        number_of_failures = 0

                time.sleep(3)

        threading.Thread(target=heartbeat_loop, daemon=True).start()
        logger.info("Heartbeat loop started")

    def stop(self):
        self.running = False


if __name__ == "__main__":
    logger.add("chunk_server.log", serialize=True)

    servers = []
    port = 8004
    for i in range(3):
        server = ChunkServer(f"chunk_server_{i}", "http://localhost:8000")
        server.start_heartbeat()
        server.server.register_function(server.store_chunk, "store_chunk")
        server.server.register_function(server.assemble_video, "assemble_video")
        servers.append(server)
        threading.Thread(target=server.server.serve_forever, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for server in servers:
            server.stop()
