import xmlrpc.server
import threading
import queue
import time
import random
from datetime import datetime
import traceback
import socketserver

# Configuration
MAX_WORKERS = 3
RPC_PORT = 9002
TASK_QUEUE = queue.Queue()

# new: simple thread-safe counters to track activity
tasks_processed = 0
active_tasks = 0
counters_lock = threading.Lock()

def worker_function(worker_id):
    """
    Worker thread that processes tasks from the queue.
    Simulates time-consuming work.
    """
    # Declare globals once at function start
    global active_tasks, tasks_processed
    
    print(f"[WORKER-{worker_id}] Started and waiting for tasks...")
    
    while True:
        try:
            # Get a task from the queue (blocks until available)
            task_data = TASK_QUEUE.get()
            
            # Check for shutdown signal
            if task_data is None:
                print(f"[WORKER-{worker_id}] Received shutdown signal")
                TASK_QUEUE.task_done()
                break
                
            print(f"[WORKER-{worker_id}] START processing task: {task_data}")
            
            # Simulate variable processing time (1-5 seconds)
            processing_time = random.randint(1, 5)
            
            # mark as active
            with counters_lock:
                active_tasks += 1
            
            time.sleep(processing_time)
            
            print(f"[WORKER-{worker_id}] FINISHED task: {task_data} (took {processing_time}s)")
            
            # update counters
            with counters_lock:
                tasks_processed += 1
                active_tasks -= 1
            
            # Mark task as completed
            TASK_QUEUE.task_done()
            
        except Exception as e:
            print(f"[WORKER-{worker_id}] Error processing task: {e}")
            # in error path, ensure we decrement active counter if we had incremented it
            with counters_lock:
                try:
                    active_tasks -= 1
                except:
                    pass
            TASK_QUEUE.task_done()

class RPCServer:
    """
    RPC Server that handles incoming requests and delegates to thread pool.
    """
    
    def __init__(self):
        self.worker_threads = []
        self.start_time = datetime.now()
        
    def start_workers(self):
        """Initialize and start the worker thread pool."""
        print(f"[SERVER] Starting {MAX_WORKERS} worker threads...")
        
        for i in range(MAX_WORKERS):
            worker = threading.Thread(
                target=worker_function,
                args=(i,),
                daemon=True
            )
            worker.start()
            self.worker_threads.append(worker)
            
        print(f"[SERVER] Worker pool initialized with {MAX_WORKERS} threads")
    
    def handle_request(self, message):
        """
        RPC method: Handles incoming requests by placing them in the task queue.
        Returns immediately to ensure high availability.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        task_id = f"TASK-{timestamp}-{hash(message) % 1000:04d}"
        
        print(f"[RPC-LISTENER] Received: '{message}' -> queued as {task_id}")
        print(f"[QUEUE-STATS] Queue size before: {TASK_QUEUE.qsize()}")
        
        # Immediate handoff to thread pool
        TASK_QUEUE.put({
            'id': task_id,
            'message': message,
            'received_at': timestamp
        })
        
        print(f"[QUEUE-STATS] Queue size after: {TASK_QUEUE.qsize()}")
        
        # Return immediate acknowledgment with a better busy metric
        with counters_lock:
            current_active = active_tasks
        
        return {
            'status': 'ACK',
            'task_id': task_id,
            'queued_at': timestamp,
            'queue_size': TASK_QUEUE.qsize(),
            'workers_busy': current_active
        }
    
    def get_stats(self):
        """RPC method: Returns server statistics."""
        with counters_lock:
            current_active = active_tasks
            total_processed = tasks_processed
        
        return {
            'uptime': str(datetime.now() - self.start_time),
            'queue_size': TASK_QUEUE.qsize(),
            'active_workers': len(self.worker_threads),
            'max_workers': MAX_WORKERS,
            'workers_busy': current_active,
            'tasks_processed': total_processed
        }
    
    def shutdown(self):
        """Gracefully shutdown the server (for testing)."""
        print("[SERVER] Shutting down worker threads...")
        
        # Send shutdown signals to all workers
        for _ in range(MAX_WORKERS):
            TASK_QUEUE.put(None)
        
        # Wait for all tasks to complete
        TASK_QUEUE.join()
        print("[SERVER] All workers shut down")

def start_server():
    """Start the RPC server and thread pool."""
    server = RPCServer()

    # Start worker thread pool
    server.start_workers()

    # Allow quick restarts on same port (set before creating the server socket)
    socketserver.TCPServer.allow_reuse_address = True

    # Start RPC server
    try:
        # bind to all interfaces so tests from other hosts work; change to 'localhost' if you prefer
        rpc_server = xmlrpc.server.SimpleXMLRPCServer(
            ('0.0.0.0', RPC_PORT),
            logRequests=False,  # Disable request logging for cleaner output
            allow_none=True
        )

        # register instance and introspection (helps diagnostics)
        rpc_server.register_instance(server)
        rpc_server.register_introspection_functions()

        print(f"[SERVER] RPC Server listening on port {RPC_PORT} (0.0.0.0)")
        print(f"[SERVER] Thread pool ready with {MAX_WORKERS} workers")
        print("[SERVER] Press Ctrl+C to stop the server")

        try:
            rpc_server.serve_forever()
        except KeyboardInterrupt:
            print("\n[SERVER] Received interrupt signal...")
            server.shutdown()
            print("[SERVER] Server stopped")
        except Exception:
            print("[SERVER] Unexpected error during serve_forever():")
            traceback.print_exc()
        finally:
            # ensure socket closed
            try:
                rpc_server.server_close()
            except Exception as e:
                print(f"[SERVER] Error closing server socket: {e}")

    except Exception:
        # Print full traceback so startup failures are visible
        print("[SERVER] Failed to start RPC server:")
        traceback.print_exc()

if __name__ == "__main__":
    start_server()
