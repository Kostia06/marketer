#!/usr/bin/env python3
"""
Lightweight webhook server that listens for GitHub push events,
pulls the latest code, and restarts the bot.

Run alongside main.py:
    nohup python3 webhook_server.py > webhook.log 2>&1 &
    nohup python3 main.py > bot.log 2>&1 &
"""

import os
import subprocess
import hmac
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("WEBHOOK_PORT", "9000"))
SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
BOT_DIR = os.path.dirname(os.path.abspath(__file__))


def verify_signature(payload: bytes, signature: str) -> bool:
    if not SECRET:
        return True
    expected = "sha256=" + hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def deploy():
    print("Pulling latest code...")
    subprocess.run(["git", "pull"], cwd=BOT_DIR, check=True)

    print("Installing dependencies...")
    venv_pip = os.path.join(BOT_DIR, "venv", "bin", "pip")
    pip_cmd = venv_pip if os.path.exists(venv_pip) else "pip"
    subprocess.run([pip_cmd, "install", "-r", "requirements.txt", "-q"], cwd=BOT_DIR)

    print("Restarting bot...")
    subprocess.run(["pkill", "-f", "python3 main.py"], cwd=BOT_DIR)
    venv_python = os.path.join(BOT_DIR, "venv", "bin", "python3")
    python_cmd = venv_python if os.path.exists(venv_python) else "python3"
    subprocess.Popen(
        [python_cmd, "main.py"],
        cwd=BOT_DIR,
        stdout=open(os.path.join(BOT_DIR, "bot.log"), "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print("Bot restarted.")


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length)
        signature = self.headers.get("X-Hub-Signature-256", "")

        if not verify_signature(payload, signature):
            self.send_response(403)
            self.end_headers()
            return

        event = self.headers.get("X-GitHub-Event", "")
        if event == "push":
            print("Push event received. Deploying...")
            deploy()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        print(f"[webhook] {args[0]}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    print(f"Webhook server listening on port {PORT}")
    server.serve_forever()
