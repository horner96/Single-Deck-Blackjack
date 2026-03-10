import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
ROOT = Path(__file__).parent
PORT = 5500
PORT = int(os.environ.get("PORT", "5500"))
STATE_LOCK = threading.Lock()
NEXT_CLIENT_ID = 1
INACTIVE_TIMEOUT_SECONDS = 45
def make_summary():
    return {"winners": [], "pushes": [], "losers": []}
GAME = {
    "clients": {},
    "players": [],
    "deck": [],
    "dealer": [],
    "turn_index": 0,
    "started": False,
    "over": False,
    "message": "Waiting for 2 players...",
    "round_summary": make_summary(),
    "dealer_resolving": False,
}
def reset_when_no_players():
    GAME.update({
        "started": False,
        "over": False,
        "dealer_resolving": False,
        "dealer": [],
        "deck": [],
        "turn_index": 0,
        "round_summary": make_summary(),
        "message": "Waiting for players...",
    })
def set_turn_message():
    GAME["message"] = f"{GAME['players'][GAME['turn_index']]['nickname']}'s turn" if 0 <= GAME["turn_index"] < len(GAME["players"]) else "Waiting for players..."
def next_player_nickname():
    used = {p["nickname"] for p in GAME["players"]}
    for candidate in ("Player 1", "Player 2"):
        if candidate not in used:
            return candidate
    return "Player"
def get_current_turn_player(client_id):
    if not GAME["started"] or GAME["over"] or len(GAME["players"]) < 2:
        return None
    if GAME["turn_index"] < 0 or GAME["turn_index"] >= len(GAME["players"]):
        return None
    current = GAME["players"][GAME["turn_index"]]
    return current if current["id"] == client_id else None
def prune_inactive_clients():
    now = time.time()
    inactive_ids = []
    for cid, info in GAME["clients"].items():
        if now - float(info.get("last_seen", 0)) > INACTIVE_TIMEOUT_SECONDS:
            inactive_ids.append(cid)
    if not inactive_ids:
        return
    for cid in inactive_ids:
        del GAME["clients"][cid]
    GAME["players"] = [p for p in GAME["players"] if p["id"] not in inactive_ids]
    if not GAME["players"]:
        reset_when_no_players()
    else:
        start_round()
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
}
def make_deck():
    suits = ["S", "H", "D", "C"]
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
    deck = [r + s for s in suits for r in ranks]
    random.shuffle(deck)
    return deck
def draw_card():
    if not GAME["deck"]:
        GAME["deck"] = make_deck()
    return GAME["deck"].pop()
def score(hand):
    total = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == "A":
            total += 11
            aces += 1
        elif rank in ("K", "Q", "J"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total
def compare(player_score, dealer_score):
    if player_score > 21:
        return "Lose (bust)"
    if dealer_score > 21:
        return "Win (dealer bust)"
    return "Win" if player_score > dealer_score else ("Push" if player_score == dealer_score else "Lose")
def start_round():
    GAME["deck"] = make_deck()
    GAME["dealer"] = [draw_card(), draw_card()]
    GAME["turn_index"] = 0
    GAME["started"] = True
    GAME["over"] = False
    GAME["dealer_resolving"] = False
    GAME["round_summary"] = make_summary()
    for p in GAME["players"]:
        p["hand"] = [draw_card(), draw_card()]
    set_turn_message()
def dealer_finish_results_only():
    dealer_score = score(GAME["dealer"])
    results = []
    summary = make_summary()
    for p in GAME["players"]:
        outcome = compare(score(p["hand"]), dealer_score)
        results.append(f"{p['nickname']}: {outcome}")
        if outcome.startswith("Win"):
            summary["winners"].append(p["nickname"])
        elif outcome == "Push":
            summary["pushes"].append(p["nickname"])
        else:
            summary["losers"].append(p["nickname"])
    GAME["over"] = True
    GAME["dealer_resolving"] = False
    GAME["turn_index"] = -1
    GAME["message"] = " | ".join(results)
    GAME["round_summary"] = summary
def run_dealer_sequence():
    with STATE_LOCK:
        if GAME["over"] or GAME["dealer_resolving"]:
            return
        GAME["dealer_resolving"] = True
        GAME["turn_index"] = -1
        GAME["message"] = "Dealer turn"
    time.sleep(1)
    while True:
        with STATE_LOCK:
            if GAME["over"]:
                return
            if score(GAME["dealer"]) <= 16:
                GAME["dealer"].append(draw_card())
                GAME["message"] = "Dealer draws..."
                should_continue = True
            else:
                should_continue = False
        if not should_continue:
            break
        time.sleep(1)
    time.sleep(1)
    with STATE_LOCK:
        if GAME["over"]:
            return
        dealer_finish_results_only()
def public_state(client_id):
    if client_id in GAME["clients"]:
        GAME["clients"][client_id]["last_seen"] = time.time()
    players = [
        {
            "id": p["id"],
            "nickname": p["nickname"],
            "hand": p["hand"],
            "score": score(p["hand"]),
        }
        for p in GAME["players"]
    ]
    return {
        "youId": client_id,
        "started": GAME["started"],
        "over": GAME["over"],
        "turnIndex": GAME["turn_index"],
        "message": GAME["message"],
        "dealerHand": GAME["dealer"],
        "dealerScore": score(GAME["dealer"]),
        "players": players,
        "roundSummary": GAME["round_summary"],
        "dealerResolving": GAME["dealer_resolving"],
    }
class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self.handle_state(parsed)
        else:
            self.serve_static(parsed.path)
    def do_POST(self):
        parsed = urlparse(self.path)
        handlers = {"/api/join": self.handle_join, "/api/action": self.handle_action, "/api/leave": self.handle_leave}
        handler = handlers.get(parsed.path)
        handler() if handler else self.send_error(404)
    def handle_state(self, parsed):
        params = parse_qs(parsed.query)
        client_id = int(params.get("clientId", ["0"])[0])
        with STATE_LOCK:
            self.send_json(public_state(client_id))
    def handle_join(self):
        global NEXT_CLIENT_ID
        self.read_json_body()
        with STATE_LOCK:
            prune_inactive_clients()
            if len(GAME["players"]) >= 2:
                self.send_json({"ok": False, "reason": "Game is full (max 2 players)."})
                return
            nickname = next_player_nickname()
            client_id = NEXT_CLIENT_ID
            NEXT_CLIENT_ID += 1
            GAME["clients"][client_id] = {"nickname": nickname, "last_seen": time.time()}
            GAME["players"].append({"id": client_id, "nickname": nickname, "hand": []})
            start_round()
            self.send_json({"ok": True, "clientId": client_id, "playerName": nickname})
    def handle_leave(self):
        body = self.read_json_body()
        client_id = int(body.get("clientId", 0) or 0)
        with STATE_LOCK:
            if client_id in GAME["clients"]:
                del GAME["clients"][client_id]
                GAME["players"] = [p for p in GAME["players"] if p["id"] != client_id]
                reset_when_no_players() if not GAME["players"] else start_round()
        self.send_json({"ok": True})
    def handle_action(self):
        body = self.read_json_body()
        client_id = int(body.get("clientId", 0))
        action = str(body.get("action", ""))
        with STATE_LOCK:
            if client_id in GAME["clients"]:
                GAME["clients"][client_id]["last_seen"] = time.time()
            if action == "newRound":
                if len(GAME["players"]) == 2:
                    start_round()
                self.send_json({"ok": True})
                return
            current = get_current_turn_player(client_id)
            if not current:
                self.send_json({"ok": True})
                return
            if action == "hit":
                current["hand"].append(draw_card())
                if score(current["hand"]) > 21:
                    GAME["turn_index"] += 1
            elif action == "stand":
                GAME["turn_index"] += 1
            if GAME["turn_index"] >= len(GAME["players"]):
                threading.Thread(target=run_dealer_sequence, daemon=True).start()
            else:
                set_turn_message()
        self.send_json({"ok": True})
    def serve_static(self, req_path):
        rel = "/index.html" if req_path in ("", "/") else req_path
        rel = unquote(rel.split("?")[0])
        full = (ROOT / rel.lstrip("/")).resolve()
        try:
            full.relative_to(ROOT)
        except ValueError:
            self.send_error(404)
            return
        if not (full.exists() and full.is_file()):
            self.send_error(404)
            return
        data = full.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(full.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
    def send_json(self, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, format, *args):
        return
if __name__ == "__main__":
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server running at http://localhost:{PORT}")
    httpd.serve_forever()
