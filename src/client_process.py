import xmlrpc.client
import time
import random
import threading
from datetime import datetime
import socket


socket.setdefaulttimeout(5)


class RPCClient:
    """
    Client that generates random messages and sends them to the server.
    """
    
    def __init__(self, server_url='http://localhost:9002/'):
        self.server = xmlrpc.client.ServerProxy(server_url, allow_none=True)
        self.request_count = 0
        
    def send_message(self, message):
        """
        Send a message to the server and handle the response.
        """
        self.request_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        try:
            print(f"[CLIENT-{timestamp}] Sending: '{message}' (Request #{self.request_count})")
            
            # Make RPC call
            start_time = time.time()
            response = self.server.handle_request(message)
            end_time = time.time()
            
            rtt = (end_time - start_time) * 1000  # Round-trip time in ms
            
            print(f"[CLIENT] Response: {response}")
            print(f"[CLIENT] Round-trip time: {rtt:.2f}ms")
            print("-" * 50)
            
            return response
            
        except Exception as e:
            print(f"[CLIENT] Error sending message: {e}")
            return None
    
    def continuous_load_test(self, duration=60, min_interval=0.5, max_interval=2.0):
        """
        Generate continuous load for testing the thread pool.
        
        Args:
            duration: How long to run the test (seconds)
            min_interval: Minimum time between requests (seconds)
            max_interval: Maximum time between requests (seconds)
        """
        print(f"[CLIENT] Starting load test for {duration} seconds...")
        print(f"[CLIENT] Request interval: {min_interval}-{max_interval} seconds")
        print("-" * 50)
        
        start_time = time.time()
        messages_sent = 0
        
        while time.time() - start_time < duration:
            # Generate random message
            message = f"Message-{messages_sent + 1}-{hash(str(time.time())) % 1000:04d}"
            
            # Send message
            self.send_message(message)
            messages_sent += 1
            
            # Random delay before next message
            delay = random.uniform(min_interval, max_interval)
            time.sleep(delay)
        
        print(f"[CLIENT] Load test completed. Sent {messages_sent} messages in {duration} seconds")
        
        # Get final server stats
        try:
            stats = self.server.get_stats()
            print(f"[CLIENT] Final server stats: {stats}")
        except:
            print("[CLIENT] Could not retrieve server stats")

def single_message_test():
    """Test with single message sending."""
    client = RPCClient()
    
    # Send a few test messages
    for i in range(5):
        message = f"Test message {i+1}"
        client.send_message(message)
        time.sleep(1)

if __name__ == "__main__":
    # Choose test mode:
    print("Choose test mode:")
    print("1. Single message test (5 messages)")
    print("2. Continuous load test (30 seconds)")
    
    # be robust in non-interactive environments (EOFError) — default to load test
    try:
        choice = input("Enter choice (1 or 2): ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "2"
    
    client = RPCClient()
    
    if choice == "1":
        single_message_test()
    else:
        # Default to load test
        client.continuous_load_test(duration=30, min_interval=0.3, max_interval=1.5)
