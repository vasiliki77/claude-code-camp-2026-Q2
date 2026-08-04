import json
import subprocess
import threading

from ..version import VERSION

PROTOCOL_VERSION = "2024-11-05"


class TransportError(Exception):
    """The server process is gone, or never spoke."""


class RpcError(Exception):
    """The server answered with a JSON-RPC error frame."""

    def __init__(self, message, rpc_code=None):
        super().__init__(message)
        self.rpc_code = rpc_code


class Client:
    """A minimal stdio MCP client.

    Boukensha is an MCP *host*: it can register tools from any MCP server, and
    the MUD is simply the server we happen to point it at. This file therefore
    contains no MUD knowledge at all — it knows a command to spawn and it knows
    JSON-RPC 2.0.

    That is the whole reason the Python port of step 10 does not reimplement
    `tools/mud.rb`. Ruby builds 26 MUD tools by hand on top of the `mud_manager`
    gem; Python asks `mud-manager --mcp` what tools it has and registers those.
    No telnet, no login dance, no Ruby library — only a subprocess.

        client = Client.spawn(command="mud-manager", args=["--mcp"])
        client.tools                    # [{"name": "look", ...}, ...]
        client.call_tool("look", {})    # {"text": "...", "error": False}
        client.close()
    """

    def __init__(self, command, args=None, env=None):
        self.command = command
        self.args = list(args or [])
        self.env = {str(k): str(v) for k, v in (env or {}).items() if v is not None}
        self._next_id = 0
        self._process = None
        self._stderr_thread = None
        self.server_info = {}
        self.tools = []

    @classmethod
    def spawn(cls, *, command, args=None, env=None):
        """Spawn and complete the handshake. One line at a call site."""
        return cls(command, args, env).start()

    def start(self):
        import os

        # The child inherits our environment with the caller's overrides layered
        # on top — same as Ruby's Open3.popen3(env, ...).
        child_env = {**os.environ, **self.env}

        self._process = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env,
            # text + bufsize=1 gives line buffering. Ruby's puts/gets work on
            # line boundaries by default; Python block-buffers a pipe unless
            # told otherwise, and a block-buffered write deadlocks this protocol
            # — the parent waits for a reply to a frame the child never received.
            text=True,
            bufsize=1,
        )

        # Anything on stderr is diagnostics, not protocol. Drain it on a thread
        # so a chatty server cannot fill the pipe buffer and deadlock the
        # conversation happening on stdout. Omitting this passes every test and
        # hangs in production, which is the worst possible failure schedule.
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "boukensha", "version": VERSION},
            },
        )
        self.server_info = result.get("serverInfo") or {}

        self._notify("notifications/initialized")

        self.tools = self._request("tools/list").get("tools") or []
        return self

    def call_tool(self, name, arguments=None):
        """Returns {"text": str, "error": bool} rather than a bare string.

        MCP models a *failed* tool call as a successful JSON-RPC result carrying
        `isError`, precisely so the model can read the failure and correct
        itself. Surfacing that structurally lets a caller decide whether to feed
        it back to the model, log it, or raise — instead of pattern-matching prose.
        """
        result = self._request(
            "tools/call", {"name": str(name), "arguments": arguments or {}}
        )
        text = "\n".join(
            block.get("text", "")
            for block in (result.get("content") or [])
            if block.get("type") == "text"
        )
        return {"text": text, "error": bool(result.get("isError"))}

    def ping(self):
        self._request("ping")
        return True

    def close(self):
        if self._process is None:
            return

        try:
            if self._process.stdin and not self._process.stdin.closed:
                self._process.stdin.close()
        except OSError:
            pass

        # The server exits when stdin closes. Give it a moment before insisting.
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()

        for stream in (self._process.stdout, self._process.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass

        self._process = None

    # Usable as a context manager, which is the idiomatic Python answer to
    # Ruby's ensure block.
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    def is_running(self):
        return self._process is not None and self._process.poll() is None

    # ---------- internals -------------------------------------------------

    @property
    def _short_name(self):
        return self.server_info.get("name") or self.command

    def _drain_stderr(self):
        try:
            for line in self._process.stderr:
                print(f"[mcp:{self._short_name}] {line.rstrip()}", flush=True)
        except (ValueError, OSError):
            # pipe closed during shutdown
            pass

    def _request(self, method, params=None):
        self._next_id += 1
        request_id = self._next_id
        frame = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params:
            frame["params"] = params
        self._write(frame)

        response = self._read_until_id(request_id)
        error = response.get("error")
        if error:
            raise RpcError(str(error.get("message")), rpc_code=error.get("code"))

        return response.get("result") or {}

    def _notify(self, method, params=None):
        frame = {"jsonrpc": "2.0", "method": method}
        if params:
            frame["params"] = params
        self._write(frame)

    def _write(self, frame):
        if self._process is None or self._process.stdin is None or self._process.stdin.closed:
            raise TransportError("MCP server is not running")

        try:
            self._process.stdin.write(json.dumps(frame) + "\n")
            self._process.stdin.flush()
        except BrokenPipeError:
            raise TransportError("MCP server closed the connection") from None

    def _read_until_id(self, request_id):
        """Skip frames that are not the reply we are waiting for — a
        server-initiated notification may legitimately arrive mid-conversation."""
        while True:
            line = self._process.stdout.readline()
            if not line:
                raise TransportError("MCP server exited without responding")

            line = line.strip()
            if not line:
                continue

            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                # Not protocol. Almost always a stray print in the server —
                # report it rather than hanging, since that bug is otherwise
                # invisible.
                print(f"[mcp:{self._short_name}] non-JSON on stdout: {line}", flush=True)
                continue

            if frame.get("id") == request_id:
                return frame
