#!/usr/bin/python3
from xmlrpc.client import ServerProxy
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

        self.stored_chunks = set()
        self.running = False
        logger.info(f"Chunk Server {server_id} initialized")

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
                    print("heartbeat error", number_of_failures)
                    number_of_failures += 1
                    if number_of_failures == 3:
                        print("election called", number_of_failures)
                        # exponentional backoff?
                        print("switched master")
                        self.master_url = self.election_proxy.current_leader()
                        print(f"new master url: {self.master_url}")
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
    for i in range(3):
        server = ChunkServer(f"chunk_server_{i}", "http://localhost:8000")
        server.start_heartbeat()
        servers.append(server)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for server in servers:
            server.stop()
