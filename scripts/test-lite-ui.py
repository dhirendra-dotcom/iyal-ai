"""LOCAL MOCK ONLY: synthetic UI checks, no Gemini/cloud calls or saved data.

Run: python scripts/test-lite-ui.py [--port 8102]
Open /app/. Chat keywords: custom (default), market, non-custom, red, demo, error,
interrupt, support. Never use this fixture as the application server.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

UI = Path(__file__).resolve().parents[1] / "frontend-lite"
PREVIEW = b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300"><rect width="600" height="300" fill="#eaf2ed"/><text x="300" y="155" text-anchor="middle" fill="#28553e" font-family="sans-serif" font-size="20">LOCAL MOCK - illustrative test fixture</text></svg>'
VERTICES = [(0, 0, 0), (25, 0, 0), (0, 20, 0), (0, 0, 75)]
STL = 'solid fixture\n' + '\n'.join('facet normal 0 0 1\nouter loop\n' + '\n'.join('vertex ' + ' '.join(map(str, VERTICES[i])) for i in face) + '\nendloop\nendfacet' for face in [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]) + '\nendsolid fixture'


class FixtureHandler(BaseHTTPRequestHandler):
    def respond(self, body, content_type="application/json", status=200):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode() if content_type == "application/json" else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ("/", "/app"):
            self.send_response(302)
            self.send_header("Location", "/app/")
            self.end_headers()
        elif url.path == "/health":
            self.respond({"status": "mock", "version": "0.13.0-fixture"})
        elif url.path.endswith("/artifacts/content"):
            if parse_qs(url.query).get("key") == ["stl"]:
                self.respond(STL, "model/stl")
            else:
                self.respond(PREVIEW, "image/svg+xml")
        elif url.path.startswith("/app/"):
            target = (UI / unquote(url.path[len('/app/'):]) ).resolve()
            if target == UI:
                target = target / "index.html"
            if not target.is_relative_to(UI) or not target.is_file():
                return self.respond({"detail": "Not found"}, status=404)
            mime = {".js": "text/javascript", ".css": "text/css"}.get(target.suffix) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.respond(target.read_bytes(), mime)
        else:
            self.respond({"detail": "Not found"}, status=404)

    def do_POST(self):
        path = urlsplit(self.path).path
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        data = json.loads(raw) if self.headers.get("Content-Type", "").startswith("application/json") else {}
        if path == "/api/sessions":
            self.respond({"user_id": "mock-user", "session_id": "mock-session"})
        elif path.endswith(("/artifacts/image", "/artifacts/video")):
            # The multipart body is deliberately discarded; no user files are stored.
            self.respond({"artifact": {"key": "mock-upload", "version": 1, "uri": "mock://upload", "mime_type": "video/mp4" if path.endswith("video") else "image/png"}})
        elif path.endswith("/transcribe"):
            self.respond({"transcript": "LOCAL MOCK: I would like a custom comfortable grip.", "model": "fixture-only"})
        elif path.endswith("/outcomes"):
            self.respond({"outcome_id": "mock-outcome", "outcome": data.get("outcome"), "message": "LOCAL MOCK: feedback accepted for this test; nothing was stored."})
        elif path.endswith("/support/book"):
            self.respond({"booking_id": "mock-booking", "date": data.get("date"), "time_slot": data.get("time_slot"), "visit_type": data.get("visit_type"), "email_status": "simulated", "message": "LOCAL MOCK: booking simulated; no email sent."})
        elif path.endswith("/chat"):
            try:
                self.chat(str(data.get("message", "")).lower())
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.respond({"detail": "Not found"}, status=404)

    def chat(self, message):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(event, data):
            self.wfile.write(f'event: {event}\ndata: {json.dumps(data)}\n\n'.encode())
            self.wfile.flush()

        def complete(tool, response):
            emit("tool_start", {"tool": tool})
            emit("tool_complete", {"tool": tool, "response": response})

        emit("connected", {"session_id": "mock-session", "heartbeat_seconds": 10})
        emit("run_started", {"session_id": "mock-session"})
        time.sleep(0.3)
        if "error" in message:
            emit("error", {"message": "LOCAL MOCK: deliberate error for testing."})
            emit("run_complete", {"session_id": "mock-session"})
            return
        custom = "non-custom" not in message and "red" not in message and "market" not in message
        market = "market" in message or not custom
        risk = "RED" if "red" in message else "GREEN"
        if market:
            complete("search_existing_products", {
                "status": "ready",
                "configured": True,
                "search_performed": True,
                "query": "adaptive spoon grip",
                "country": "India",
                "market_text": "LOCAL MOCK market research: current search found foam build-up grips and adaptive utensil handles. Fit still depends on the spoon-handle dimensions.",
                "sources": [
                    {"title": "Example grip listing", "url": "https://example.com/grip"},
                    {"title": "Example utensil listing", "url": "https://example.org/utensil"},
                ],
                "source_count": 2,
                "failure_reason": None,
                "disclaimer": "LOCAL MOCK: source links are synthetic test fixtures.",
            })
        complete("present_adaptation_options", {"status": "ready", "context_type": "object", "problem_summary": "LOCAL MOCK scenario", "user_goal": "Use a spoon comfortably", "task": "Eating", "object_name": "Spoon", "functional_barrier": "The standard handle feels too bulky", "decision_rationale": "A slimmer grip addresses the reported fit gap.", "risk_reason": "Mock risk assessment for UI testing only.", "recommended_strategy": "custom_cad" if custom else "change_technique", "requires_measurement": custom, "professional_review_recommended": risk == "RED", "usage_evidence_required": False, "risk_level": risk, "custom_design_requested": custom, "market_check_skipped": not market, "options": [{"strategy": "custom_cad" if custom else "change_technique", "title": "LOCAL MOCK recommendation", "rationale": "Synthetic example", "requires_measurement": custom, "requires_professional": risk == "RED"}]})
        if custom:
            complete("validate_design", {"valid": True})
            complete("generate_3d_design", {"status": "success"})
            emit("design_ready", {"design_version": 1, "artifact_key": "fixture.stl", "artifact_version": 1, "stl_path": "/api/sessions/mock-session/artifacts/content?key=stl", "design": {"outer_width_mm": 25, "outer_depth_mm": 20, "grip_length_mm": 75, "profile": "oval", "texture": "smooth", "measurement_source": "user_provided", "demo_only": "demo" in message}, "mesh": {"watertight": True}})
            emit("tool_start", {"tool": "generate_usage_preview"})
            time.sleep(2)
            if "interrupt" in message:
                return
            emit("tool_complete", {"tool": "generate_usage_preview", "response": {"status": "success"}})
            emit("preview_ready", {"artifact_key": "preview", "artifact_version": 1, "image_path": "/api/sessions/mock-session/artifacts/content?key=preview", "label": "LOCAL MOCK preview", "disclaimer": "Synthetic fixture. Not a real design or verified fit."})
            complete("assess_support_need", {"status": "ready", "risk_level": risk, "evidence_quality": "moderate", "data_completeness": 0.8, "measurement_confidence": 0.72, "image_quality": 0.74, "physical_fit_verified": False})
            complete("offer_product_support", {"status": "ready", "risk_level": risk, "review_priority": "recommended", "title": "LOCAL MOCK fit review", "description": "Synthetic form; no booking or email will be sent.", "reason": "Mock evidence has moderate uncertainty.", "evidence_quality": "moderate", "available_dates": [{"date": "2026-10-19", "label": "Mock date: 19 October", "times": ["10:00", "14:00"]}], "visit_types": ["video_review"]})
        if "interrupt" in message:
            return
        emit("final", {"text": "LOCAL MOCK: this synthetic response tests the interface. No model or cloud services were called."})
        emit("run_complete", {"session_id": "mock-session"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8102)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), FixtureHandler)
    print(f"LOCAL MOCK ONLY: http://127.0.0.1:{args.port}/app/ — no model calls or saved data", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
