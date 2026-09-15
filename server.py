import os
import sys
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", 10000))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"SHAKH SPACE bot is running!")

    def log_message(self, format, *args):
        pass


def start_web():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print("WEB SERVER ISHLAYAPTI", flush=True)
    server.serve_forever()


threading.Thread(target=start_web, daemon=True).start()

print("BOT ISHGA TUSHIRILMOQDA...", flush=True)

process = subprocess.Popen(
    [sys.executable, "-u", "bot.py"],
    stdout=sys.stdout,
    stderr=sys.stderr
)

print("BOT PROCESS ISHLAYAPTI", flush=True)

exit_code = process.wait()

print(f"BOT TO'XTADI. CODE: {exit_code}", flush=True)

sys.exit(1)
