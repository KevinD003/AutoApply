"""Runs inside a fresh network namespace (via `unshare -n`), before Chromium. Stdlib only.

1. Brings up the namespace's loopback interface (the namespace has no other interface,
   so no route, DNS or database is reachable).
2. Forks a relay: TCP 127.0.0.1:<port> (inside the namespace) -> UNIX socket of the egress
   proxy outside. This is the only way out.
3. Execs Chromium with --proxy-server pointing at the relay and loopback no longer bypassed.

Usage: netns_boot.py SOCKET PORT CHROME [chrome args...]
"""

import asyncio
import fcntl
import os
import socket
import struct
import sys
import time

SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1


def loopback_up():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ifr = struct.pack("16sH14s", b"lo", 0, b"")
    flags = struct.unpack("16sH14s", fcntl.ioctl(s, SIOCGIFFLAGS, ifr))[1]
    fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack("16sH14s", b"lo", flags | IFF_UP, b""))
    s.close()


async def relay(sock_path: str, port: int, ready_fd: int, parent: int):
    async def handle(r, w):
        try:
            ur, uw = await asyncio.open_unix_connection(sock_path)
        except OSError:
            w.close()
            return

        async def pipe(a, b):
            try:
                while data := await a.read(65536):
                    b.write(data)
                    await b.drain()
            except OSError:
                pass
            finally:
                b.close()

        await asyncio.gather(pipe(r, uw), pipe(ur, w))

    await asyncio.start_server(handle, "127.0.0.1", port)
    os.write(ready_fd, b"1")
    os.close(ready_fd)
    while os.getppid() == parent:  # exit with Chromium
        await asyncio.sleep(0.5)


def main():
    sock_path, port, chrome, args = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4:]
    loopback_up()
    rd, wr = os.pipe()
    parent = os.getpid()
    if os.fork() == 0:
        os.close(rd)
        for fd in (3, 4):  # Chromium's DevTools pipes belong to the parent only
            try:
                os.close(fd)
            except OSError:
                pass
        asyncio.run(relay(sock_path, port, wr, parent))
        os._exit(0)
    os.close(wr)
    deadline = time.monotonic() + 10
    while not os.read(rd, 1) and time.monotonic() < deadline:
        pass
    os.close(rd)
    proxy = [f"--proxy-server=http://127.0.0.1:{port}", "--proxy-bypass-list=<-loopback>"]
    os.execv(chrome, [chrome, *args, *proxy])


if __name__ == "__main__":
    main()
