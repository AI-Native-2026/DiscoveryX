#!/usr/bin/env python3
"""Minimal SSH helper for DiscoveryX VM provisioning.

Auth order:
  1. If DX_VM_KEY (default ~/.ssh/discoveryx_vm) exists -> key auth.
  2. Else use DX_VM_PASS (password auth), used only for the initial key install.

Usage:
  python vm_ssh.py "uname -a"
  python vm_ssh.py --install-key
  python vm_ssh.py --put <local> <remote>
"""
import argparse
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass


def _client(force_password: bool = False, attempts: int = 5):
    import time

    import paramiko

    host = os.environ["DX_VM_HOST"]
    user = os.environ.get("DX_VM_USER", "ubuntu")
    key_path = os.environ.get("DX_VM_KEY", os.path.expanduser("~/.ssh/discoveryx_vm"))

    last_exc: Exception | None = None
    for i in range(1, attempts + 1):
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if not force_password and os.path.exists(key_path):
                c.connect(hostname=host, username=user, key_filename=key_path, timeout=30, banner_timeout=30)
                if os.environ.get("DX_VM_VERBOSE"):
                    print(f"[auth] key {key_path}")
            else:
                pw = os.environ.get("DX_VM_PASS")
                if not pw:
                    sys.exit("DX_VM_PASS not set and no key found")
                c.connect(hostname=host, username=user, password=pw, timeout=30, banner_timeout=30)
                if os.environ.get("DX_VM_VERBOSE"):
                    print("[auth] password")
            return c
        except Exception as exc:  # noqa: BLE001 - retry transient SSH failures
            last_exc = exc
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
            if i < attempts:
                print(f"[ssh] attempt {i}/{attempts} failed ({type(exc).__name__}), retrying…", file=sys.stderr)
                time.sleep(3 * i)
    raise SystemExit(f"SSH connection failed after {attempts} attempts: {last_exc}")


def run(cmd: str, timeout: int = 600) -> int:
    import shlex

    c = _client()
    try:
        wrapped = "bash -lc " + shlex.quote(cmd)
        stdin, stdout, stderr = c.exec_command(wrapped, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        if out:
            sys.stdout.write(out)
        if err:
            sys.stderr.write(err)
        return code
    finally:
        c.close()


def install_key() -> int:
    pub = os.path.expanduser(os.environ.get("DX_VM_PUBKEY", "~/.ssh/discoveryx_vm.pub"))
    if not os.path.exists(pub):
        sys.exit(f"public key not found: {pub}")
    with open(pub, encoding="utf-8") as f:
        pubkey = f.read().strip()
    cmd = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        f"grep -qxF '{pubkey}' ~/.ssh/authorized_keys 2>/dev/null || echo '{pubkey}' >> ~/.ssh/authorized_keys; "
        "chmod 600 ~/.ssh/authorized_keys && echo KEY_INSTALLED"
    )
    c = _client(force_password=True)
    try:
        stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
        print(stdout.read().decode("utf-8", "replace"))
        print(stderr.read().decode("utf-8", "replace"))
        return stdout.channel.recv_exit_status()
    finally:
        c.close()


def put(local: str, remote: str) -> int:
    c = _client()
    try:
        sftp = c.open_sftp()
        sftp.put(local, remote)
        print(f"put {local} -> {remote}")
        sftp.close()
        return 0
    finally:
        c.close()


def get(remote: str, local: str) -> int:
    c = _client()
    try:
        sftp = c.open_sftp()
        sftp.get(remote, local)
        print(f"get {remote} -> {local}")
        sftp.close()
        return 0
    finally:
        c.close()


def run_script(local: str, timeout: int = 1800) -> int:
    c = _client()
    remote = "/tmp/dx_remote_script.sh"
    try:
        sftp = c.open_sftp()
        sftp.put(local, remote)
        sftp.close()
        stdin, stdout, stderr = c.exec_command(
            f"bash {remote}; rc=$?; rm -f {remote}; exit $rc", timeout=timeout
        )
        sys.stdout.write(stdout.read().decode("utf-8", "replace"))
        sys.stderr.write(stderr.read().decode("utf-8", "replace"))
        return stdout.channel.recv_exit_status()
    finally:
        c.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?")
    ap.add_argument("--install-key", action="store_true")
    ap.add_argument("--put", nargs=2, metavar=("LOCAL", "REMOTE"))
    ap.add_argument("--get", nargs=2, metavar=("REMOTE", "LOCAL"))
    ap.add_argument("--script", metavar="LOCAL")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    if args.install_key:
        return install_key()
    if args.put:
        return put(args.put[0], args.put[1])
    if args.get:
        return get(args.get[0], args.get[1])
    if args.script:
        return run_script(args.script, args.timeout)
    if not args.command:
        ap.error("command required")
    return run(args.command, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
