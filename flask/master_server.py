#!/usr/bin/python3
import os
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.client import ServerProxy
from loguru import logger
import time
import sys
import random

class MasterServer:
    def __init__(self, host, port):
        self.server = SimpleXMLRPCServer(
            ("localhost", port), logRequests=False, allow_none=True
        )

        if port == 8000:
            self.leader = True
            self.backup = "http://localhost:8001"
            self.backup_master = ServerProxy(self.backup)
            logger.info("This server is the leader master")
        else:
            self.leader = False
            self.backup = None
            self.backup_master = None
            logger.info("This server is a backup master")

        # System state
        self.chunk_servers = {}
        self.videos = {}
        self.uploads_today = 0
        self.last_reset = time.time()

        self.job_locations = {}

        self.setup_methods()
        logger.info(f"Master Server initialized on {host}:{port}")

    def setup_methods(self):
        self.server.register_function(self.ping)
        self.server.register_function(self.heartbeat)
        self.server.register_function(self.register_video)
        self.server.register_function(self.get_system_status)
        self.server.register_function(self.get_chunk_servers)
        self.server.register_function(self.register_chunk)
        self.server.register_function(self.list_videos)
        self.server.register_function(self.get_video_details)
        self.server.register_function(self.set_job_locations)
        self.server.register_function(self.become_leader)
    
    def become_leader(self):
        self.leader = True
        logger.info("This server has become the leader master")
        return True

    def ping(self):
        return "pong"

    def heartbeat(self, server_id, server_info):
        current_time = time.time()
        self.chunk_servers[server_id] = {
            "last_heartbeat": current_time,
            "info": server_info,
            "status": "healthy",
        }
        if self.leader:
            try:
                self.backup_master.heartbeat(server_id, server_info)
                logger.debug(
                    f"Heartbeat replicated to backup for {server_id}",
                    server_id=server_id,
                )
            except Exception as e:
                logger.error(f"Failed to replicate heartbeat to backup: {e}")

        logger.info(
            f"Heartbeat from {server_id}",
            server_id=server_id,
            load=server_info.get("load", 0),
        )
        return {"status": "ack", "timestamp": current_time}

    def set_job_locations(self, job_locations):
        self.job_locations = job_locations
        return True

    def register_video(self, video_data, job_id):
        video_id = video_data["video_id"]
        self.videos[video_id] = video_data
        self.uploads_today += 1

        logger.info(
            "Video registered",
            video_id=video_id,
            title=video_data["title"],
            chunk_count=video_data["chunk_count"],
        )

        current_chunk_server = self.job_locations.get(job_id)
        if current_chunk_server:
            try:
                proxy = ServerProxy(f"http://localhost:{8005 + int(current_chunk_server["id"].split('_')[-1])}")
                video_data = proxy.assemble_video(job_id)
                logger.debug(
                    f"Video metadata sent to chunk server {current_chunk_server['id']}",
                    chunk_server=current_chunk_server,
                    video_id=video_id,
                )
                for chunk_server in self.chunk_servers.keys():
                    if chunk_server != current_chunk_server['id']:
                        os.makedirs(f"videos/{chunk_server}", exist_ok=True)
                        path = os.path.join(f"videos/{chunk_server}", f"{chunk_server}_video_{job_id}.mp4")
                        if hasattr(video_data, "data"):      
                            data = video_data.data
                        with open(path, "wb") as f:
                            f.write(data)
            except Exception as e:
                logger.error(
                    f"Failed to send video metadata to chunk server {current_chunk_server['id']}: {e}",
                    chunk_server=current_chunk_server,
                    video_id=video_id,
                )
        else:
            logger.warning(
                f"No chunk server found for job {job_id} to notify about video {video_id}",
                job_id=job_id,
                video_id=video_id,
            )

        return {"status": "registered", "video_id": video_id}

    def get_system_status(self):
        if time.time() - self.last_reset > 86400:
            self.uploads_today = 0
            self.last_reset = time.time()

        active_servers = sum(
            1
            for s in self.chunk_servers.values()
            if time.time() - s["last_heartbeat"] < 60
        )

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

    def get_chunk_servers(self, job_id):
        active_servers = []
        current_time = time.time()

        for server_id, server_data in self.chunk_servers.items():
            if current_time - server_data["last_heartbeat"] < 60:
                active_servers.append(
                    {
                        "id": server_id,
                        "status": server_data["status"],
                        "last_seen": server_data["last_heartbeat"],
                        "info": server_data["info"],
                    }
                )
        if job_id in self.job_locations:
            return self.job_locations[job_id]
        server = active_servers[random.randint(0, len(active_servers)-1)] if active_servers else None
        self.job_locations[job_id] = server
        if self.leader:
            try:
                self.backup_master.set_job_locations(self.job_locations)
                logger.debug(
                    f"Job location for job {job_id} replicated to backup",
                    job_id=job_id,
                    server=server,
                )
            except Exception as e:
                logger.error(f"Failed to replicate job location to backup: {e}")
        return server

    def register_chunk(self, chunk_id, server_id, video_id):
        logger.debug(
            "Chunk registered",
            chunk_id=chunk_id,
            server_id=server_id,
            video_id=video_id,
        )
        if self.leader and self.backup_master:
            try:
                self.backup_master.register_chunk(chunk_id, server_id, video_id)
                logger.debug(
                    "Chunk registration replicated to backup",
                    chunk_id=chunk_id,
                    server_id=server_id,
                    video_id=video_id,
                )
            except Exception as e:
                logger.error(f"Failed to replicate chunk registration to backup: {e}")
        return True

    def list_videos(self):
        video_list = []
        for video_id, video_data in self.videos.items():
            video_list.append(
                {
                    "video_id": video_id,
                    "title": video_data.get("title", "Unknown"),
                    "filename": video_data.get("filename", "Unknown"),
                    "chunk_count": video_data.get("chunk_count", 0),
                    "total_size": video_data.get("total_size", 0),
                    "upload_time": video_data.get("upload_time", 0),
                }
            )
        return video_list

    def get_video_details(self, video_id):
        if video_id in self.videos:
            return self.videos[video_id]
        return None

    def serve_forever(self):
        logger.info("Starting XML-RPC master server...")
        self.server.serve_forever()


if __name__ == "__main__":
    logger.add("master_server.log", serialize=True, rotation="10 MB")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = MasterServer("localhost", port)
    server.serve_forever()