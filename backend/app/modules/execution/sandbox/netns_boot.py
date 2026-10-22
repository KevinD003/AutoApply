"""Runs inside fresh network, PID and mount namespaces (via `unshare`), before Chromium.
Stdlib only.

1. Brings up the namespace's loopback interface (the namespace has no other interface,
   so no route, DNS or database is reachable).
2. Forks a relay: TCP 127.0.0.1:<port> (inside the namespace) -> UNIX socket of the egress
   proxy outside. This is the only way out.
3. In a second mount namespace (so the relay keeps its view), hides paths that hold the
   orchestrator's code, configuration and data: each hidden directory becomes an empty
   read-only tmpfs, each hidden file /dev/null. /tmp is replaced by a tmpfs that contains only
   this browser's own work directory, so other attempts' egress sockets are out of reach.
4. Enters a nested user + mount namespace. Mounts inherited from a more privileged namespace
   are locked: the browser, although uid 0 inside, cannot unmount them to look underneath.
5. Changes to its own work directory, closes every inherited descriptor except stdio and
   the DevTools pipes, and execs Chromium with --proxy-server pointing at the relay and
   loopback no longer bypassed.

The PID namespace (with its own /proc, mounted by unshare) means no process outside the
browser's own tree is visible, so the worker's environment cannot be read via /proc.

Usage: netns_boot.py SOCKET PORT WORKDIR HIDE CHROME [chrome args...]
HIDE is an os.pathsep-separated list of paths (may be empty).
"""

import asyncio
import ctypes
import fcntl
import os
import socket
import struct
import sys
import time

SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1
MS_RDONLY, MS_NOSUID, MS_NODEV, MS_NOEXEC = 0x1, 0x2, 0x4, 0x8
MS_REMOUNT, MS_BIND, MS_MOVE = 0x20, 0x1000, 0x2000
_libc = ctypes.CDLL("libc.so.6", use_errno=True)


def _mount(src, target, fstype, flags, data=None):
    enc = lambda v: v.encode() if isinstance(v, str) else v  # noqa: E731
    if _libc.mount(enc(src), enc(target), enc(fstype), flags, enc(data)) != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"mount {target}: {os.strerror(err)}")


def loopback_up():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ifr = struct.pack("16sH14s", b"lo", 0, b"")
    flags = struct.unpack("16sH14s", fcntl.ioctl(s, SIOCGIFFLAGS, ifr))[1]
    fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack("16sH14s", b"lo", flags | IFF_UP, b""))
    s.close()


def hide_paths(paths, workdir):
    ro = MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC
    for p in paths:
        if not p or not os.path.lexists(p):
            continue
        if os.path.isdir(p) and not os.path.islink(p):
            _mount("none", p, "tmpfs", ro, "size=4k,mode=0555")
        elif os.path.isfile(p):
            _mount("/dev/null", p, None, MS_BIND)
    # /tmp holds only our work directory: build the replacement inside the work directory,
    # bind the work directory into it, then move it over /tmp.
    tmp = os.path.realpath("/tmp")
    work = os.path.realpath(workdir)
    if os.path.commonpath([tmp, work]) == tmp:
        stage = os.path.join(work, ".tmp-root")
        os.makedirs(stage, 0o700, exist_ok=True)
        _mount("none", stage, "tmpfs", MS_NOSUID | MS_NODEV, "size=64m,mode=1777")
        inner = os.path.join(stage, os.path.relpath(work, tmp))
        os.makedirs(inner, 0o700, exist_ok=True)
        _mount(work, inner, None, MS_BIND)
        _mount(stage, tmp, None, MS_MOVE)


def enter_locked_namespace():
    uid, gid = os.getuid(), os.getgid()
    os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS)
    with open("/proc/self/setgroups", "w") as f:
        f.write("deny")
    with open("/proc/self/uid_map", "w") as f:
        f.write(f"0 {uid} 1")
    with open("/proc/self/gid_map", "w") as f:
        f.write(f"0 {gid} 1")


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
    sock_path, port, workdir, hide = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    chrome, args = sys.argv[5], sys.argv[6:]
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
    try:
        os.unshare(os.CLONE_NEWNS)  # the relay keeps the unhidden view
        hide_paths([p for p in hide.split(os.pathsep) if p], workdir)
        enter_locked_namespace()
        # The inherited working directory still points into the (now hidden) worker tree,
        # because a mount does not move processes already inside it. Leave it.
        os.chdir(workdir)
    except OSError as e:  # fail closed; the error's text (paths) is not printed
        sys.exit(f"netns_boot: cannot isolate the filesystem ({type(e).__name__})")
    # Only stdio and Chromium's DevTools pipes (3, 4) may cross into the browser.
    os.closerange(5, os.sysconf("SC_OPEN_MAX"))
    proxy = [f"--proxy-server=http://127.0.0.1:{port}", "--proxy-bypass-list=<-loopback>"]
    os.execv(chrome, [chrome, *args, *proxy])


if __name__ == "__main__":
    main()
