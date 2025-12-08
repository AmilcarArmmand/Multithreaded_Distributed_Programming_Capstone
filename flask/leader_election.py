import threading
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.client import ServerProxy
from loguru import logger
import time

class LeaderElection:
    def __init__(self):
        self.leader = "http://localhost:8000"
        self.backup = "http://localhost:8001"
        self.down_server = None
        self.server = SimpleXMLRPCServer(('localhost', 9000), allow_none=True)
        self.lock = threading.Lock()

        self.backup_check_thread = threading.Thread(target=self.check_backup, daemon=True)
        self.backup_check_thread.start()

        self.master_heartbeat_thread = threading.Thread(target=self.master_heartbeat, daemon=True)
        self.master_heartbeat_thread.start()
    
    def ping_down_server(self):
        proxy = ServerProxy(self.down_server)
        try:
            proxy.ping()
            logger.info(f"Server {self.down_server} is back online.")
            with self.lock:
                self.backup = self.down_server
                self.down_server = None
            return True
        except:
            logger.info(f"Server {self.down_server} still down.")
            return False
    
    def check_backup(self):
        while True:
            with self.lock:
                backup = self.backup
                down_server = self.down_server

            if backup is None and down_server is not None:
                logger.warning("No backup server available!")
                exponentional_backoff = 1
                while not self.ping_down_server():
                    time.sleep(exponentional_backoff)
                    exponentional_backoff = min(exponentional_backoff * 2, 60)
            time.sleep(1)

    def election(self):
        with self.lock:
            self.down_server = self.leader
            self.leader, self.backup = self.backup, None
            logger.info(f"New leader elected: {self.leader}")

    def current_leader(self):
        print("Current leader requested", self.leader)
        return self.leader
    
    def start_backup(self, backup_url):
        with self.lock:
            self.backup = backup_url
            logger.info(f"Backup server set to: {self.backup}")
    
    def master_heartbeat(self):
        while True:
            with self.lock:
                leader = self.leader
            try:
                proxy = ServerProxy(leader)
                proxy.ping()
            except:
                logger.error(f"Leader {leader} is down! Initiating election.")
                self.election()
            time.sleep(1)
    
def main():
    leader_election = LeaderElection()
    leader_election.server.register_function(leader_election.election, "election")
    leader_election.server.register_function(leader_election.current_leader, "current_leader")
    logger.info("Leader Election server started on port 9000")
    leader_election.server.serve_forever()

if __name__ == "__main__":
    logger.add("leader_election.log", serialize=True)
    main()