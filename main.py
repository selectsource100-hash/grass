import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# This creates a tiny web server so Render is happy
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Grass Node is Running!")

def run_fake_server():
    # Render provides the PORT variable automatically
    import os
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"Fake server started on port {port}")
    server.serve_forever()

# Start the fake server in a background thread
threading.Thread(target=run_fake_server, daemon=True).start()

# --- YOUR ORIGINAL GRASS CODE STARTS HERE ---
import asyncio
# ... (rest of your script)


import asyncio
import ssl
import json
import time
import uuid
import websockets

# --- PASTE YOUR INFO HERE ---
USER_ID = "38ac1IpkYWxDOmJn2afZVN5h6tX" 
# ----------------------------

async def connect_to_wss():
    device_id = str(uuid.uuid4())
    print(f"Starting Grass Node for User: {USER_ID} | Device: {device_id}")
    
    while True:
        try:
            await asyncio.sleep(1)
            uri = "wss://proxy.wynd.network:4650/"
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            async with websockets.connect(uri, ssl=ssl_context) as websocket:
                async def send_ping():
                    while True:
                        send_message = json.dumps({
                            "id": str(uuid.uuid4()), "version": "1.0.0", "action": "PING", "data": {}
                        })
                        await websocket.send(send_message)
                        await asyncio.sleep(20)

                asyncio.create_task(send_ping())

                while True:
                    response = await websocket.recv()
                    data = json.loads(response)
                    if data.get("action") == "AUTH":
                        auth_response = json.dumps({
                            "id": data["id"],
                            "origin_action": "AUTH",
                            "result": {
                                "browser_id": device_id,
                                "user_id": USER_ID,
                                "user_agent": "Mozilla/5.0",
                                "timestamp": int(time.time()),
                                "extension_id": "lkbnfiajjnggjhnakneomhioebonidbe",
                                "version": "2.5.0"
                            }
                        })
                        await websocket.send(auth_response)
                    elif data.get("action") == "PONG":
                        print("PONG received - Connection Active")
        except Exception as e:
            print(f"Error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

asyncio.run(connect_to_wss())
