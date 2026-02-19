"""
Student Admin System - Python Backend
Uses only Python standard library (no pip install needed)
Run with: python app.py
Server starts at: http://localhost:8000
"""

import json
import os
import csv
import io
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# ─────────────────────────────────────────────
# IN-MEMORY DATA STORE  (persists to JSON file)
# ─────────────────────────────────────────────
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"students": [], "selections": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

db = load_data()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def json_response(handler, status, payload):
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", len(body))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
    handler.end_headers()
    handler.wfile.write(body)

def file_response(handler, status, content, content_type, filename=None):
    body = content if isinstance(content, bytes) else content.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", len(body))
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)

def read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(length)) if length else {}

# ─────────────────────────────────────────────
# REQUEST HANDLER
# ─────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}]  {self.address_string()}  {format % args}")

    # ── OPTIONS (CORS preflight) ──────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.end_headers()

    # ── GET ───────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        # Serve index.html
        if path in ("/", "/index.html"):
            try:
                with open("index.html", "rb") as f:
                    file_response(self, 200, f.read(), "text/html")
            except FileNotFoundError:
                json_response(self, 404, {"error": "index.html not found"})

        # List all students (admin)
        elif path == "/api/students":
            json_response(self, 200, {"students": db["students"]})

        # List all selections (admin)
        elif path == "/api/selections":
            json_response(self, 200, {"selections": db["selections"]})

        # Export selections as CSV
        elif path == "/api/export/csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Register No", "NME", "Activity", "Submitted At"])
            for s in db["selections"]:
                writer.writerow([s["reg"], s["nme"], s["activity"], s.get("timestamp", "")])
            file_response(self, 200, output.getvalue(), "text/csv", "selections.csv")

        # Summary stats
        elif path == "/api/stats":
            total_students  = len(db["students"])
            total_submitted = len(db["selections"])
            nme_counts      = {}
            act_counts      = {}
            for s in db["selections"]:
                nme_counts[s["nme"]]      = nme_counts.get(s["nme"], 0) + 1
                act_counts[s["activity"]] = act_counts.get(s["activity"], 0) + 1
            json_response(self, 200, {
                "total_students":  total_students,
                "total_submitted": total_submitted,
                "nme_breakdown":   nme_counts,
                "activity_breakdown": act_counts,
            })

        else:
            json_response(self, 404, {"error": "Not found"})

    # ── POST ──────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        body = read_body(self)

        # ── Admin login ──
        if path == "/api/admin/login":
            if body.get("username") == ADMIN_USERNAME and body.get("password") == ADMIN_PASSWORD:
                json_response(self, 200, {"success": True, "message": "Admin authenticated"})
            else:
                json_response(self, 401, {"success": False, "message": "Invalid credentials"})

        # ── Add student (admin) ──
        elif path == "/api/admin/add-student":
            reg    = body.get("reg", "").strip()
            dob    = body.get("dob", "").strip()
            if not reg or not dob:
                json_response(self, 400, {"success": False, "message": "Register number and DOB are required"})
                return
            if any(s["reg"] == reg for s in db["students"]):
                json_response(self, 409, {"success": False, "message": f"Student {reg} already exists"})
                return
            db["students"].append({"reg": reg, "dob": dob, "added_at": datetime.now().isoformat()})
            save_data(db)
            json_response(self, 201, {"success": True, "message": f"Student {reg} added successfully"})

        # ── Student login ──
        elif path == "/api/student/login":
            reg = body.get("reg", "").strip()
            dob = body.get("dob", "").strip()
            match = next((s for s in db["students"] if s["reg"] == reg and s["dob"] == dob), None)
            if match:
                already = any(s["reg"] == reg for s in db["selections"])
                json_response(self, 200, {"success": True, "already_submitted": already})
            else:
                json_response(self, 401, {"success": False, "message": "Student not registered by Admin!"})

        # ── Save student selection ──
        elif path == "/api/student/select":
            reg      = body.get("reg", "").strip()
            nme      = body.get("nme", "").strip()
            activity = body.get("activity", "").strip()
            if not reg or not nme or not activity:
                json_response(self, 400, {"success": False, "message": "Missing fields"})
                return
            # Update if already exists, else append
            existing = next((i for i, s in enumerate(db["selections"]) if s["reg"] == reg), None)
            entry = {"reg": reg, "nme": nme, "activity": activity, "timestamp": datetime.now().isoformat()}
            if existing is not None:
                db["selections"][existing] = entry
            else:
                db["selections"].append(entry)
            save_data(db)
            json_response(self, 200, {"success": True, "message": "Selection saved!"})

        else:
            json_response(self, 404, {"error": "Not found"})

    # ── DELETE ────────────────────────────────
    def do_DELETE(self):
        path = urlparse(self.path).path

        # Delete a student by reg no: DELETE /api/admin/student/<reg>
        if path.startswith("/api/admin/student/"):
            reg = path.split("/")[-1]
            before = len(db["students"])
            db["students"]  = [s for s in db["students"]  if s["reg"] != reg]
            db["selections"] = [s for s in db["selections"] if s["reg"] != reg]
            if len(db["students"]) < before:
                save_data(db)
                json_response(self, 200, {"success": True, "message": f"Student {reg} deleted"})
            else:
                json_response(self, 404, {"success": False, "message": "Student not found"})
        else:
            json_response(self, 404, {"error": "Not found"})


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    PORT = 8000
    server = HTTPServer(("", PORT), Handler)
    print("=" * 50)
    print("  Student Admin System – Backend Server")
    print("=" * 50)
    print(f"  Running at:  http://localhost:{PORT}")
    print(f"  Data file:   {os.path.abspath(DATA_FILE)}")
    print(f"  Admin creds: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
