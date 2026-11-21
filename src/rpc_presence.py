import json
import os
import socket
import struct
import threading
import time
import uuid

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4


def _socket_paths():
    bases = []
    for var in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
        value = os.environ.get(var)
        if value:
            bases.append(value.rstrip("/"))
    bases.append("/tmp")
    seen = set()
    for base in bases:
        for sub in ("", "app/com.discordapp.Discord/", "snap.discord/"):
            for i in range(10):
                path = f"{base}/{sub}discord-ipc-{i}"
                if path not in seen:
                    seen.add(path)
                    yield path


def _pack(op, payload):
    data = json.dumps(payload).encode("utf-8")
    return struct.pack("<II", op, len(data)) + data


class RpcPresence:
    """
    Registers a Rich Presence activity for a Discord application id through the
    local Discord IPC socket. Does not need any executable to be running.
    """
    def __init__(self, app_id):
        self.app_id = str(app_id)
        self.sock = None
        self.alive = False
        self.error = None
        self.thread = None

    def _read_frame(self, timeout):
        self.sock.settimeout(timeout)
        header = self._read_exact(8)
        op, length = struct.unpack("<II", header)
        body = self._read_exact(length) if length else b""
        return op, json.loads(body.decode("utf-8")) if body else {}

    def _read_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Discord closed the IPC connection")
            buf += chunk
        return buf

    def start(self):
        last_error = "Discord IPC socket not found. Is Discord running?"
        for path in _socket_paths():
            if not os.path.exists(path):
                continue
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                s.settimeout(5)
                s.connect(path)
                self.sock = s
                s.sendall(_pack(OP_HANDSHAKE, {"v": 1, "client_id": self.app_id}))
                op, msg = self._read_frame(10)
                if msg.get("evt") != "READY":
                    last_error = f"Discord refused the handshake: {msg.get('data', msg)}"
                    s.close()
                    self.sock = None
                    continue
                activity = {
                    "timestamps": {"start": int(time.time())},
                    "instance": False
                }
                s.sendall(_pack(OP_FRAME, {
                    "cmd": "SET_ACTIVITY",
                    "args": {"pid": os.getpid(), "activity": activity},
                    "nonce": str(uuid.uuid4())
                }))
                op, msg = self._read_frame(10)
                if msg.get("evt") == "ERROR":
                    last_error = f"Discord rejected the activity: {msg.get('data', msg)}"
                    s.close()
                    self.sock = None
                    continue
                self.alive = True
                self.thread = threading.Thread(target=self._loop, daemon=True)
                self.thread.start()
                return True
            except Exception as e:
                last_error = str(e)
                try:
                    s.close()
                except Exception:
                    pass
                self.sock = None
        self.error = last_error
        return False

    def _loop(self):
        while self.alive:
            try:
                op, msg = self._read_frame(30)
            except socket.timeout:
                continue
            except Exception:
                self.alive = False
                return
            if op == OP_PING:
                try:
                    self.sock.sendall(_pack(OP_PONG, msg))
                except Exception:
                    self.alive = False
                    return
            elif op == OP_CLOSE:
                self.alive = False
                return

    def is_alive(self):
        return self.alive

    def stop(self):
        was_alive = self.alive
        self.alive = False
        if self.sock:
            try:
                if was_alive:
                    self.sock.sendall(_pack(OP_FRAME, {
                        "cmd": "SET_ACTIVITY",
                        "args": {"pid": os.getpid()},
                        "nonce": str(uuid.uuid4())
                    }))
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
