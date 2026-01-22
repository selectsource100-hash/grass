import asyncio
import websockets
import json
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- KEEP ALIVE SERVER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Node is Alive")

def run_fake_server():
    import os
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_fake_server, daemon=True).start()

# --- NODEPAY SCRIPT ---
USER_ID = "38ac1IpkYWxDOmJn2afZVN5h6tX" # Your ID

async def run_node():
    uri = "wss://nw.nodepay.ai:443/websocket" # Nodepay's address
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                print("Connected to Nodepay!")
                # Authenticate and start earning
                auth_data = {"action": "auth", "data": {"token": USER_ID}}
                await websocket.send(json.dumps(auth_data))
                while True:
                    resp = await websocket.recv()
                    print(f"Earning Update: {resp}")
                    await asyncio.sleep(30)
        except Exception as e:
            print(f"Connection lost, retrying... {e}")
            await asyncio.sleep(10)

asyncio.run(run_node())
