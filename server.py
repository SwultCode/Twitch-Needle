import os
import asyncio
import json
import logging
import time
import certifi
from dotenv import load_dotenv
from twitchio import Client
from flask import Flask, render_template_string, Response
from hypercorn.asyncio import serve
from hypercorn.config import Config

# Set up logging
logging.basicConfig(level=logging.INFO)

# Use certifi's certificates
os.environ['SSL_CERT_FILE'] = certifi.where()

# Load environment variables
load_dotenv()
TWITCH_CHANNEL = os.getenv("TWITCH_CHANNEL")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
PORT = int(os.getenv("PORT", "8080"))
if not TWITCH_CHANNEL or not TWITCH_TOKEN:
    raise ValueError("Please ensure TWITCH_CHANNEL and TWITCH_TOKEN are set in your .env file.")

# Create Flask app
app = Flask(__name__)

# Global counter (updated by the Twitch bot)
counter = 0

# SSE endpoint that continuously streams the current counter value.
@app.route("/stream")
def stream():
    def event_stream():
        last_value = None
        # Check for counter changes every 0.1 second for high responsiveness
        while True:
            global counter
            if counter != last_value:
                data = json.dumps({"counter": counter})
                yield f"data: {data}\n\n"
                last_value = counter
            time.sleep(0.05)
    return Response(event_stream(), mimetype="text/event-stream")

# Serve a simple HTML page with a green background and a counter
@app.route("/")
def index():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Counter Display</title>
      <style>
        body {
          background-color: #FFFFFF;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .gauge-container {
          position: relative;
          width: 400px;
          height: 200px;
          margin: 20px;
        }
        #gauge {
          position: absolute;
          width: 100%;
          height: 100%;
          z-index: 1;
          transform: scale(0.9);
        }
        #needle {
          position: absolute;
          width: 100%;
          height: 100%;
          z-index: 2;
          transform-origin: bottom center;
          transition: transform 0.3s ease;
        }
        #counter {
          font-size: 64px;
          font-weight: bold;
          position: absolute;
          left: 50%;
          top: 40%;
          transform: translate(-50%, -50%);
          z-index: 3;
          color: #000000;
          font-family: Arial, Helvetica, sans-serif;
        }
        #reset-button {
          margin-top: 20px;
          padding: 10px 20px;
          background: #ffffff;
          color: #000000;
          border: 2px solid #333;
          border-radius: 5px;
          cursor: pointer;
          font-size: 14px;
        }
        .instructions {
          font-size: 12px;
          color: #333;
          margin: 10px 0;
          background: white;
          padding: 5px;
        }
      </style>
    </head>
    <body>
      <div class="gauge-container">
        <div id="counter">0</div>
        <img id="gauge" src="/static/images/Gauge.svg" alt="speed gauge">
        <img id="needle" src="/static/images/Needle.svg" alt="needle indicator">
      </div>
      <div class="instructions">Click button below to reset counter</div>
      <button id="reset-button" onclick="handleReset()">Reset Counter</button>
      <button id="shutdown-button" onclick="handleShutdown()" style="margin-top: 10px; padding: 10px 20px; background: #ff4444; color: white; border: 2px solid #cc0000; border-radius: 5px; cursor: pointer; font-size: 14px;">Shutdown Server</button>
      <script>
        async function handleShutdown() {
          if (confirm('Are you sure you want to shutdown the server?')) {
            try {
              await fetch('/shutdown', { method: 'POST' });
              alert('Server is shutting down...');
            } catch (error) {
              console.error('Error:', error);
            }
          }
        }

        async function handleReset() {
          try {
            const response = await fetch('/reset', { method: 'POST' });
            if (!response.ok) throw new Error('Reset failed');
            document.getElementById('counter').innerText = '0';
            document.getElementById('needle').style.transform = 'rotate(0deg)';
          } catch (error) {
            console.error('Error:', error);
          }
        }

        const evtSource = new EventSource("/stream");
        evtSource.onmessage = function(event) {
          try {
            const data = JSON.parse(event.data);
            const angle = Math.tanh(data.counter / 500) * 90;
            document.getElementById('needle').style.transform = `rotate(${angle}deg)`;
            document.getElementById("counter").innerText = data.counter;
          } catch (e) {
            console.error("Error parsing message:", e);
          }
        };
        evtSource.onerror = function(error) {
          console.error("EventSource error:", error);
        };
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

# Twitch bot that listens for "+2" and "-2" in chat to update the counter.
class TwitchBot(Client):
    async def event_ready(self):
        print(f"Logged in as: {self.nick}", flush=True)
    async def event_message(self, message):
        global counter
        content = message.content.strip().lower()
        if  "+2" in content:
            counter += 2
        elif "-2" in content:
            counter -= 2

# Main function to run both the Twitch bot and the Flask app concurrently
async def main():
    bot = TwitchBot(token=TWITCH_TOKEN, initial_channels=[TWITCH_CHANNEL])
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    await asyncio.gather(
        bot.start(),
        serve(app, config)
    )

# New reset endpoint
@app.route('/reset', methods=['POST'])
def reset_counter():
    global counter
    counter = 0
    return '', 204

# Shutdown endpoint
@app.route('/shutdown', methods=['POST'])
def shutdown():
    os._exit(0)

if __name__ == "__main__":
    asyncio.run(main())
