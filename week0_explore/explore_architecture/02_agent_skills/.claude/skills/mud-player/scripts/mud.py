#!/usr/bin/env python3
"""
mud.py - persistent session manager for a telnet MUD.

A MUD connection is stateful, but agent tool calls are one-shot: every fresh
`nc` would land you back at the login screen with your room, fight, and buffs
gone. So a background daemon owns the socket for the whole play session, and
each CLI call is a thin client that talks to it over a Unix socket.

    start    connect + log in + enter the game (idempotent)
    send     send a command, return the output it produced
    read     drain output that arrived on its own (combat, tells, wandering mobs)
    expect   block until some text shows up (or time out)
    status   is the session alive, and what are the current vitals
    log      tail the transcript
    stop     quit the character out cleanly and shut the daemon down

Everything the MUD ever sent is appended to transcript.log, so history
survives even though individual commands return only what is new.
"""

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time

# --- Telnet protocol bytes (RFC 854) ---
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")

# TBAMUD/CircleMUD prompt, e.g. "22H 100M 83V (news) (motd) > ".
# Reaching this means the server finished the command and wants more input,
# which is a far tighter completion signal than guessing with a sleep.
PROMPT_RE = re.compile(r"\d+H\s+\d+M\s+\d+V[^\n]*>\s*$")
VITALS_RE = re.compile(r"(\d+)H\s+(\d+)M\s+(\d+)V")
# CircleMUD pages long output and waits for a keypress; left unattended this
# stalls the session mid-page, so the daemon walks pagers itself.
PAGER_RE = re.compile(r"\[ Return to continue[^\]]*\]\s*$")
# Once a pager has been walked, its control line is noise in the returned text.
PAGER_LINE_RE = re.compile(r"\[ Return to continue[^\]]*\]")

DEFAULT_STATE = os.path.expanduser("~/.mud-player")


def state_dir(args):
    d = args.state or os.environ.get("MUD_STATE_DIR") or DEFAULT_STATE
    d = os.path.join(d, f"{args.host}-{args.port}")
    os.makedirs(d, exist_ok=True)
    return d


def paths(sd):
    return {
        "sock": os.path.join(sd, "control.sock"),
        "pid": os.path.join(sd, "daemon.pid"),
        "log": os.path.join(sd, "transcript.log"),
        "err": os.path.join(sd, "daemon.err"),
    }


def strip_ansi(b):
    return ANSI_RE.sub(b"", b)


# --------------------------------------------------------------------------
# Daemon
# --------------------------------------------------------------------------

class Session:
    def __init__(self, host, port, user, password, logpath):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.logpath = logpath
        self.sock = None
        self.buf = ""            # cleaned text received so far
        self.lock = threading.Lock()
        self.connected = False
        self.error = None
        self.logged_in = False

    # -- low level io --

    def _negotiate(self, data):
        """Strip telnet control sequences, refusing every option.

        The server opens with IAC DO TERMINAL-TYPE. Ignoring it leaves 0xFF
        bytes in the text and can hang the handshake, so refuse cleanly and
        keep only the human-readable payload.
        """
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b == IAC and i + 1 < len(data):
                c = data[i + 1]
                if c in (DO, DONT) and i + 2 < len(data):
                    self.sock.sendall(bytes([IAC, WONT, data[i + 2]]))
                    i += 3
                    continue
                if c in (WILL, WONT) and i + 2 < len(data):
                    self.sock.sendall(bytes([IAC, DONT, data[i + 2]]))
                    i += 3
                    continue
                if c == SB:
                    j = data.find(bytes([IAC, SE]), i)
                    i = j + 2 if j != -1 else len(data)
                    continue
                i += 2
                continue
            out.append(b)
            i += 1
        return bytes(out)

    def _reader(self):
        """Continuously drain the socket so output is never lost between calls."""
        pending = b""
        while self.connected:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            pending += chunk
            # A telnet sequence can straddle a recv boundary; hold back a
            # trailing partial rather than corrupting it.
            cut = len(pending)
            if pending and pending[-1] == IAC:
                cut -= 1
            elif len(pending) >= 2 and pending[-2] == IAC:
                cut -= 2
            data, pending = pending[:cut], pending[cut:]
            if not data:
                continue
            text = strip_ansi(self._negotiate(data)).decode("utf-8", "replace")
            text = text.replace("\r\n", "\n").replace("\r", "")
            with self.lock:
                self.buf += text
            try:
                with open(self.logpath, "a") as f:
                    f.write(text)
            except OSError:
                pass
        self.connected = False

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.sock.settimeout(0.5)
        self.connected = True
        threading.Thread(target=self._reader, daemon=True).start()

    def write(self, text):
        self.sock.sendall((text + "\r\n").encode("utf-8", "replace"))

    # -- buffer helpers --

    def tail(self, n=400):
        with self.lock:
            return self.buf[-n:]

    def mark(self):
        with self.lock:
            return len(self.buf)

    def since(self, mark):
        with self.lock:
            return self.buf[mark:]

    def wait_for(self, pattern, timeout, mark=None):
        """Block until `pattern` appears after `mark`. Returns (matched, text)."""
        rx = re.compile(pattern) if isinstance(pattern, str) else pattern
        if mark is None:
            mark = self.mark()
        deadline = time.time() + timeout
        while time.time() < deadline:
            text = self.since(mark)
            if rx.search(text):
                return True, text
            if not self.connected:
                return False, text
            time.sleep(0.05)
        return False, self.since(mark)

    # -- login --

    def login(self, timeout=45):
        """Walk the login screens by waiting for each prompt.

        The flow is name -> password -> a "PRESS RETURN" gate -> the account
        menu. Blind timed sends desync the moment the server pauses, so match
        on whatever prompt actually arrives and answer that.
        """
        deadline = time.time() + timeout
        sent = set()
        while time.time() < deadline:
            if not self.connected:
                self.error = "connection closed during login"
                return False
            tail = self.tail(600)

            # A second password prompt after we already answered one means the
            # credentials were refused; without this the loop would just spin
            # until the timeout and report a vague failure.
            with self.lock:
                pw_prompts = len(re.findall(r"password:", self.buf, re.I))
            if "pass" in sent and pw_prompts >= 2:
                self.error = "password rejected by server"
                return False

            if re.search(r"(by what name|what is your name|name:)", tail, re.I) and "name" not in sent:
                self.write(self.user)
                sent.add("name")
            elif re.search(r"password:", tail, re.I) and "pass" not in sent:
                self.write(self.password)
                sent.add("pass")
            elif re.search(r"press return", tail, re.I) and "return" not in sent:
                self.write("")
                sent.add("return")
            elif re.search(r"make your choice", tail, re.I):
                self.write("1")  # 1) Enter the game
                ok, _ = self.wait_for(PROMPT_RE, 15)
                self.logged_in = ok
                if not ok:
                    self.error = "entered menu choice but never reached a game prompt"
                return ok
            elif re.search(r"(incorrect|wrong password|invalid)", tail, re.I):
                self.error = "login rejected by server"
                return False
            elif PROMPT_RE.search(tail):
                self.logged_in = True
                return True

            time.sleep(0.2)
        self.error = "timed out waiting for a login prompt"
        return False

    # -- command execution --

    def run(self, text, timeout=10, max_pages=20):
        """Send a command and return the output it produced.

        Waits for the prompt rather than a fixed sleep, and clears any pager
        so a long `help` or `who` does not leave the session wedged.
        """
        mark = self.mark()
        self.write(text)
        pages = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.connected:
                break
            out = self.since(mark)
            tail = out[-400:]
            if PAGER_RE.search(tail) and pages < max_pages:
                self.write("")
                pages += 1
                time.sleep(0.15)
                continue
            if PROMPT_RE.search(tail):
                time.sleep(0.15)  # let a trailing async line land
                return PAGER_LINE_RE.sub("", self.since(mark))
            time.sleep(0.05)
        return PAGER_LINE_RE.sub("", self.since(mark))

    def drain(self, wait):
        """Collect whatever arrives on its own over `wait` seconds."""
        mark = self.mark()
        time.sleep(wait)
        return self.since(mark)

    def vitals(self):
        m = None
        for m in VITALS_RE.finditer(self.tail(2000)):
            pass
        if not m:
            return None
        return {"hp": int(m.group(1)), "mana": int(m.group(2)), "moves": int(m.group(3))}


def serve(args, sd):
    p = paths(sd)
    sess = Session(args.host, args.port, args.user, args.password, p["log"])
    try:
        sess.connect()
    except OSError as e:
        sys.stderr.write(f"connect failed: {e}\n")
        return 1
    if not sess.login():
        sys.stderr.write(f"login failed: {sess.error}\n")
        return 1

    if os.path.exists(p["sock"]):
        os.unlink(p["sock"])
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(p["sock"])
    srv.listen(8)
    srv.settimeout(1.0)

    with open(p["pid"], "w") as f:
        f.write(str(os.getpid()))

    running = True
    while running:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            if not sess.connected:
                break
            continue
        try:
            conn.settimeout(120)
            raw = b""
            while not raw.endswith(b"\n"):
                c = conn.recv(65536)
                if not c:
                    break
                raw += c
            if not raw:
                conn.close()
                continue
            req = json.loads(raw.decode())
            op = req.get("op")
            resp = {"ok": True, "connected": sess.connected}

            if op == "send":
                resp["output"] = sess.run(req["text"], req.get("timeout", 10))
            elif op == "read":
                resp["output"] = sess.drain(req.get("wait", 2))
            elif op == "expect":
                matched, text = sess.wait_for(req["pattern"], req.get("timeout", 30))
                resp["matched"], resp["output"] = matched, text
            elif op == "status":
                resp["logged_in"] = sess.logged_in
                state = "in game" if sess.logged_in else "connected, not in game"
                resp["output"] = (f"session: {state} as {sess.user} "
                                  f"@ {sess.host}:{sess.port}\n"
                                  f"--- recent output ---\n{sess.tail(400)}")
            elif op == "stop":
                try:
                    sess.run("quit", timeout=5)
                except OSError:
                    pass
                resp["output"] = "session closed"
                running = False
            else:
                resp = {"ok": False, "error": f"unknown op {op!r}"}

            resp["vitals"] = sess.vitals()
            conn.sendall((json.dumps(resp) + "\n").encode())
        except Exception as e:  # never let one bad client kill the session
            try:
                conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
            except OSError:
                pass
        finally:
            conn.close()

    sess.connected = False
    try:
        sess.sock.close()
    except (OSError, AttributeError):
        pass
    srv.close()
    for f in (p["sock"], p["pid"]):
        if os.path.exists(f):
            os.unlink(f)
    return 0


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

def call(sd, req, timeout=180):
    p = paths(sd)
    if not os.path.exists(p["sock"]):
        return None
    try:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.settimeout(timeout)
        c.connect(p["sock"])
        c.sendall((json.dumps(req) + "\n").encode())
        raw = b""
        while not raw.endswith(b"\n"):
            chunk = c.recv(65536)
            if not chunk:
                break
            raw += chunk
        c.close()
        return json.loads(raw.decode()) if raw else None
    except (OSError, json.JSONDecodeError):
        return None


def alive(sd):
    p = paths(sd)
    if not os.path.exists(p["pid"]):
        return False
    try:
        with open(p["pid"]) as f:
            os.kill(int(f.read().strip()), 0)
        return os.path.exists(p["sock"])
    except (OSError, ValueError):
        return False


def render(resp, show_vitals=True):
    if resp is None:
        print("no live session - run: mud.py start", file=sys.stderr)
        return 1
    if not resp.get("ok"):
        print(f"error: {resp.get('error')}", file=sys.stderr)
        return 1
    out = (resp.get("output") or "").strip("\n")
    if out:
        print(out)
    if show_vitals and resp.get("vitals"):
        v = resp["vitals"]
        print(f"\n[hp {v['hp']} | mana {v['mana']} | moves {v['moves']}]")
    if not resp.get("connected", True):
        print("\n[session disconnected]", file=sys.stderr)
    if resp.get("matched") is False:
        print("[expect: pattern did not appear before timeout]", file=sys.stderr)
    return 0


def cmd_start(args, sd):
    if alive(sd):
        print("session already running")
        return render(call(sd, {"op": "status"}))
    p = paths(sd)
    for f in (p["sock"], p["pid"]):
        if os.path.exists(f):
            os.unlink(f)
    open(p["log"], "a").close()

    err = open(p["err"], "w")
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__),
         "--host", args.host, "--port", str(args.port),
         "--user", args.user, "--password", args.password,
         "--state", args.state or os.environ.get("MUD_STATE_DIR") or DEFAULT_STATE,
         "_serve"],
        stdout=err, stderr=err, stdin=subprocess.DEVNULL, start_new_session=True,
    )
    for _ in range(int(args.timeout * 10)):
        if alive(sd):
            print(f"connected to {args.host}:{args.port} as {args.user}")
            return render(call(sd, {"op": "status"}))
        time.sleep(0.1)
    err.close()
    msg = ""
    if os.path.exists(p["err"]):
        with open(p["err"]) as f:
            msg = f.read().strip()
    print(f"failed to start session. {msg}", file=sys.stderr)
    return 1


def first_line(text):
    """Pull the server's acknowledgement out of a command's output."""
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not PROMPT_RE.search(line):
            return line
    return "(no response)"


# Settings worth having on for agent play: (table label, command, desired).
# Brief is deliberately OFF - it hides room descriptions, which is most of
# what you need in order to decide where to go next.
DESIRED_TOGGLES = [
    ("AutoExits", "autoexits", "ON"),
    ("AutoLoot", "autoloot", "ON"),
    ("AutoGold", "autogold", "ON"),
    ("Brief", "brief", "OFF"),
]

TOGGLE_ROW_RE = re.compile(r"([A-Za-z][A-Za-z ]*?):\s*(ON|OFF|\d+)\b", re.I)


def read_toggles(sd):
    """Return the character's current preference table as {label: value}."""
    r = call(sd, {"op": "send", "text": "toggle", "timeout": 10}, timeout=45)
    if r is None or not r.get("ok"):
        return None, r
    state = {m.group(1).strip(): m.group(2).upper()
             for m in TOGGLE_ROW_RE.finditer(r.get("output") or "")}
    return state, r


def cmd_setup(args, sd):
    """Apply the settings that make agent play workable, idempotently.

    These commands are *toggles*, not switches: the server ignores a trailing
    `on`, so sending `autoexits` blindly flips it off whenever it was already
    on. Since the settings persist on the character between sessions, a naive
    re-run at each login would silently undo itself every other time. So read
    the current table first and only send the ones actually out of place.
    """
    state, err = read_toggles(sd)
    if state is None:
        return render(err)

    for label, cmd, want in DESIRED_TOGGLES:
        cur = state.get(label)
        if cur is None:
            print(f"{label:<12} not supported on this server, skipping")
            continue
        if cur == want:
            print(f"{label:<12} already {want}")
            continue
        r = call(sd, {"op": "send", "text": cmd, "timeout": 10}, timeout=45)
        if r is None or not r.get("ok"):
            return render(r)
        print(f"{label:<12} {cur} -> {want}: {first_line(r.get('output'))}")

    # `toggle wimpy N` sets an absolute threshold, so it is already idempotent.
    if args.wimpy is not None:
        r = call(sd, {"op": "send", "text": f"toggle wimpy {args.wimpy}",
                      "timeout": 10}, timeout=45)
        if r is None or not r.get("ok"):
            return render(r)
        print(f"{'Wimpy':<12} {first_line(r.get('output'))}")
    return 0


def cmd_stop(sd):
    if not alive(sd):
        print("no session running")
        return 0
    call(sd, {"op": "stop"}, timeout=20)
    time.sleep(0.5)
    p = paths(sd)
    if os.path.exists(p["pid"]):
        try:
            with open(p["pid"]) as f:
                os.kill(int(f.read().strip()), signal.SIGTERM)
        except (OSError, ValueError):
            pass
    print("session closed")
    return 0


def cmd_reset(sd):
    """Reset character to temple by relogging.

    Quits the current session and reconnects, which returns the character
    to a known safe location (Temple of Midgaard) or allows recovery from
    stuck states.
    """
    if not alive(sd):
        print("no session running", file=sys.stderr)
        return 1

    print("resetting character to safe state...")
    call(sd, {"op": "stop"}, timeout=20)
    time.sleep(1)

    # Kill the daemon
    p = paths(sd)
    for f in (p["pid"], p["sock"]):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    time.sleep(1)

    # Reconnect
    return cmd_start(argparse.Namespace(
        host="localhost", port=4000, user="dummy", password="helloworld",
        state=None, timeout=60
    ), sd)


def main():
    ap = argparse.ArgumentParser(description="Persistent MUD session manager")
    ap.add_argument("--host", default=os.environ.get("MUD_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MUD_PORT", 4000)))
    ap.add_argument("--user", default=os.environ.get("MUD_USER", "dummy"))
    ap.add_argument("--password", default=os.environ.get("MUD_PASSWORD", "helloworld"))
    ap.add_argument("--state", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="connect and log in")
    s.add_argument("--timeout", type=float, default=60)
    sub.add_parser("_serve")  # internal: the daemon body

    s = sub.add_parser("send", help="send one or more commands")
    s.add_argument("text", nargs="+")
    s.add_argument("--timeout", type=float, default=10)
    s.add_argument("--quiet", action="store_true", help="suppress the vitals line")

    s = sub.add_parser("read", help="drain unsolicited output")
    s.add_argument("--wait", type=float, default=2)

    s = sub.add_parser("expect", help="wait for text to appear")
    s.add_argument("pattern")
    s.add_argument("--timeout", type=float, default=30)

    s = sub.add_parser("setup", help="apply agent-friendly game settings (idempotent)")
    s.add_argument("--wimpy", type=int, default=None,
                   help="auto-flee below this many HP; omit to leave unchanged")

    sub.add_parser("status", help="show session state")
    sub.add_parser("stop", help="quit and shut down")
    sub.add_parser("reset", help="quit and reconnect (returns to temple)")

    s = sub.add_parser("log", help="tail the transcript")
    s.add_argument("-n", type=int, default=60)

    args = ap.parse_args()
    sd = state_dir(args)

    if args.cmd == "_serve":
        return serve(args, sd)
    if args.cmd == "start":
        return cmd_start(args, sd)
    if args.cmd == "stop":
        return cmd_stop(sd)
    if args.cmd == "reset":
        return cmd_reset(sd)
    if args.cmd == "setup":
        if not alive(sd):
            print("no session running (start one with: mud.py start)", file=sys.stderr)
            return 1
        return cmd_setup(args, sd)
    if args.cmd == "log":
        p = paths(sd)
        if not os.path.exists(p["log"]):
            print("no transcript yet", file=sys.stderr)
            return 1
        with open(p["log"]) as f:
            lines = f.read().splitlines()
        print("\n".join(lines[-args.n:]))
        return 0
    if args.cmd == "status":
        if not alive(sd):
            print("no session running (start one with: mud.py start)")
            return 1
        return render(call(sd, {"op": "status"}))
    if args.cmd == "send":
        # Multiple args run in order, so a movement chain is one tool call.
        rc, last = 0, None
        for t in args.text:
            last = call(sd, {"op": "send", "text": t, "timeout": args.timeout},
                        timeout=args.timeout + 30)
            if last is None or not last.get("ok"):
                return render(last)
            if len(args.text) > 1:
                print(f"--- {t} ---")
            rc |= render(last, show_vitals=False)
        if last and last.get("vitals") and not args.quiet:
            v = last["vitals"]
            print(f"\n[hp {v['hp']} | mana {v['mana']} | moves {v['moves']}]")
        return rc
    if args.cmd == "read":
        return render(call(sd, {"op": "read", "wait": args.wait}, timeout=args.wait + 30))
    if args.cmd == "expect":
        return render(call(sd, {"op": "expect", "pattern": args.pattern,
                                "timeout": args.timeout}, timeout=args.timeout + 30))
    return 1


if __name__ == "__main__":
    sys.exit(main())
