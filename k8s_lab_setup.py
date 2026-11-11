#!/usr/bin/env python3
"""
k8s_lab_setup.py - Install + validate tools for a local Kubernetes lab (Linux Mint)

Installs ONLY what the lab needs (skips anything already installed):
  - Docker Engine
  - kubectl
  - kind (Kubernetes in Docker)

It does NOT create clusters, nodes, pods, or change any system settings.

Usage (from VS Code terminal, as normal user - not root):
  python3 k8s_lab_setup.py             # install missing tools, then validate
  python3 k8s_lab_setup.py --validate  # validate only, install nothing
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

KIND_VERSION = os.environ.get("KIND_VERSION", "v0.27.0")


# ---------- helpers ----------
def log(msg):
    print(f"\n\033[1;36m==> {msg}\033[0m", flush=True)


def run(cmd, check=True, capture=False, input_text=None):
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(
        cmd, check=check, text=True, input=input_text,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def have(binary):
    return shutil.which(binary) is not None


def arch():
    m = platform.machine().lower()
    return {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(m, "amd64")


def os_release():
    data = {}
    with open("/etc/os-release") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                data[k] = v.strip('"')
    return data


def download(url, dest):
    print(f"Downloading {url}", flush=True)
    urllib.request.urlretrieve(url, dest)


def apt_update():
    """apt-get update, but don't die on a broken THIRD-PARTY repo (common on desktops)."""
    r = run(["sudo", "apt-get", "update"], check=False)
    if r.returncode != 0:
        print("\n\033[1;33mWARNING: apt update reported errors (likely a broken third-party repo).\033[0m")
        print("Continuing - package lists for working repos are still updated.")
        print("To find the bad entry:  grep -rn 'kubernetes.io\\|k8s.io' /etc/apt/sources.list /etc/apt/sources.list.d/")


# ---------- installers ----------
def install_docker():
    if have("docker"):
        log("Docker already installed - skipping")
        return
    log("Installing Docker Engine (official repo)")
    rel = os_release()
    codename = rel.get("UBUNTU_CODENAME") or rel.get("VERSION_CODENAME")  # Mint -> Ubuntu base
    if not codename:
        sys.exit("Could not detect Ubuntu codename from /etc/os-release")

    apt_update()
    run(["sudo", "apt-get", "install", "-y", "ca-certificates", "curl", "gnupg"])
    run(["sudo", "install", "-m", "0755", "-d", "/etc/apt/keyrings"])
    run(["sudo", "curl", "-fsSL", "https://download.docker.com/linux/ubuntu/gpg",
         "-o", "/etc/apt/keyrings/docker.asc"])
    run(["sudo", "chmod", "a+r", "/etc/apt/keyrings/docker.asc"])

    repo = (f"deb [arch={arch()} signed-by=/etc/apt/keyrings/docker.asc] "
            f"https://download.docker.com/linux/ubuntu {codename} stable\n")
    run(["sudo", "tee", "/etc/apt/sources.list.d/docker.list"], input_text=repo, capture=True)
    apt_update()
    run(["sudo", "apt-get", "install", "-y", "docker-ce", "docker-ce-cli", "containerd.io",
         "docker-buildx-plugin", "docker-compose-plugin"])
    run(["sudo", "systemctl", "enable", "--now", "docker"])

    user = os.environ.get("USER") or os.getlogin()
    log(f"Adding {user} to docker group (so you can run docker without sudo)")
    run(["sudo", "usermod", "-aG", "docker", user])


def install_kubectl():
    if have("kubectl"):
        log("kubectl already installed - skipping")
        return
    log("Installing kubectl")
    with urllib.request.urlopen("https://dl.k8s.io/release/stable.txt") as r:
        ver = r.read().decode().strip()
    tmp = os.path.join(tempfile.gettempdir(), "kubectl")
    download(f"https://dl.k8s.io/release/{ver}/bin/linux/{arch()}/kubectl", tmp)
    run(["sudo", "install", "-m", "0755", tmp, "/usr/local/bin/kubectl"])


def install_kind():
    if have("kind"):
        log("kind already installed - skipping")
        return
    log(f"Installing kind {KIND_VERSION}")
    tmp = os.path.join(tempfile.gettempdir(), "kind")
    download(f"https://kind.sigs.k8s.io/dl/{KIND_VERSION}/kind-linux-{arch()}", tmp)
    run(["sudo", "install", "-m", "0755", tmp, "/usr/local/bin/kind"])


# ---------- validation ----------
def capture(cmd):
    r = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, (r.stdout or "").strip()


def validate():
    log("Validating tools")
    results = []  # (name, ok, detail)

    # Docker binary
    if have("docker"):
        rc, out = capture(["docker", "--version"])
        results.append(("docker binary", rc == 0, out))
    else:
        results.append(("docker binary", False, "not found"))

    # Docker daemon running (system level)
    rc, out = capture(["systemctl", "is-active", "docker"])
    results.append(("docker service", out == "active", out or "unknown"))

    # Docker group membership for current user
    _, groups = capture(["id", "-nG"])
    _, db_groups = capture(["getent", "group", "docker"])
    user = os.environ.get("USER") or ""
    in_group_db = user in db_groups.split(":")[-1].split(",") if db_groups else False
    in_session = "docker" in groups.split()
    if in_session:
        results.append(("docker group (current shell)", True, "active"))
    elif in_group_db:
        results.append(("docker group (current shell)", False,
                        "added, but not active yet -> log out/in (or reboot) once"))
    else:
        results.append(("docker group (current shell)", False, "user not in docker group"))

    # Docker daemon reachable without sudo
    if have("docker"):
        rc, out = capture(["docker", "info", "--format", "{{.ServerVersion}}"])
        results.append(("docker daemon access", rc == 0,
                        f"server {out}" if rc == 0 else "cannot connect without sudo"))

    # kubectl
    if have("kubectl"):
        rc, out = capture(["kubectl", "version", "--client"])
        first = out.splitlines()[0] if out else ""
        results.append(("kubectl", rc == 0, first))
    else:
        results.append(("kubectl", False, "not found"))

    # kind
    if have("kind"):
        rc, out = capture(["kind", "version"])
        results.append(("kind", rc == 0, out))
    else:
        results.append(("kind", False, "not found"))

    # Print report
    print()
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        mark = "\033[1;32m[ OK ]\033[0m" if ok else "\033[1;31m[FAIL]\033[0m"
        print(f"{mark} {name.ljust(width)}  {detail}")

    failed = [n for n, ok, _ in results if not ok]
    print()
    if failed:
        print(f"\033[1;31mValidation failed:\033[0m {', '.join(failed)}")
        if any("docker group" in n or "daemon access" in n for n in failed) and have("docker"):
            print("Tip: log out and back in (or reboot) so the docker group takes effect, "
                  "then run: python3 k8s_lab_setup.py --validate")
        return False
    print("\033[1;32mAll tools installed and working.\033[0m No clusters were created.")
    return True


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Install + validate K8s lab tools (Docker, kubectl, kind)")
    ap.add_argument("--validate", action="store_true", help="validate only, install nothing")
    args = ap.parse_args()

    if os.geteuid() == 0:
        sys.exit("Don't run as root/sudo - run as your normal user (script uses sudo when needed).")
    if platform.system() != "Linux":
        sys.exit("This script is for Linux.")

    if not args.validate:
        install_docker()
        install_kubectl()
        install_kind()

    ok = validate()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
