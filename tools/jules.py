#!/usr/bin/env python3
import subprocess
try:
    import winreg
except ImportError:
    winreg = None
import sys
import json
import os
import socket
import argparse
import requests
import urllib3
from pathlib import Path

# Disable insecure request warnings when using verify=False over local Clash proxy
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_env_token():
    # 1. Try system environment
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    # 2. Try searching upwards for a local .env file
    base_dir = Path(__file__).resolve().parent
    for path in [base_dir, base_dir.parent, base_dir.parent.parent]:
        env_file = path / ".env"
        if env_file.exists():
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == "GITHUB_TOKEN":
                                return v.strip()
            except Exception:
                pass
    return None

TOKEN = get_env_token()
REPO = "RebeccaKaku/OptiFolio"
URL = f"https://api.github.com/repos/{REPO}/issues"


def detect_active_proxy():
    """Detects the active proxy using Registry, Env vars, and active port probing."""
    # 1. Check Registry (Windows only)
    if winreg:
        try:
            registry_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            )
            proxy_enable, _ = winreg.QueryValueEx(registry_key, "ProxyEnable")
            if proxy_enable == 1:
                proxy_server, _ = winreg.QueryValueEx(registry_key, "ProxyServer")
                if proxy_server:
                    if ";" in proxy_server:
                        parts = proxy_server.split(";")
                        for part in parts:
                            if part.startswith("https=") or part.startswith("http="):
                                return part.split("=")[1]
                    return proxy_server
        except Exception:
            pass

    # 2. Check Env Vars
    for var in ["HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "ALL_PROXY"]:
        val = os.environ.get(var)
        if val:
            clean_val = val
            for prefix in ["http://", "https://", "socks5://", "socks5h://"]:
                if clean_val.startswith(prefix):
                    clean_val = clean_val[len(prefix):]
            return clean_val

    # 3. Probe Common Ports on localhost
    common_ports = [7897, 7890, 10809, 1080]
    for port in common_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return f"127.0.0.1:{port}"
        except Exception:
            pass

    return None

def get_current_branch():
    """Gets the name of the active Git branch."""
    try:
        return subprocess.check_output(
            ["git", "symbolic-ref", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        try:
            return subprocess.check_output(
                ["git", "branch", "--show-current"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            return "main"

def run_git_command(args):
    """Helper to execute git commands and display output."""
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True
        )
        print(result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(e.stdout.strip())
        return False

def run_git_push(proxy, remote_url, branch):
    """Pushes branch to remote using secure OpenSSL backend and SSL bypass."""
    git_base = ["git"]
    if winreg:
        git_base += [
            "-c", "http.sslBackend=openssl",
            "-c", "http.sslVerify=false"
        ]
    if proxy:
        proxy_url = f"http://{proxy}"
        print(f"[*] Attempting Git push via proxy: {proxy_url}...")
        push_cmd = git_base + ["-c", f"http.proxy={proxy_url}", "push", remote_url, branch]
        try:
            subprocess.run(push_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[+] Git push via proxy succeeded!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[-] Git push via proxy failed: {e.stderr.decode().strip()}")

    print("[*] Attempting Git push directly (no proxy)...")
    push_cmd_direct = git_base + ["-c", "http.proxy=", "push", remote_url, branch]
    try:
        subprocess.run(push_cmd_direct, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("[+] Git push directly succeeded!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[-] Git push directly failed: {e.stderr.decode().strip()}")
        return False

def main():
    if not TOKEN:
        print("[-] Error: GITHUB_TOKEN not found in environment or .env file.")
        print("[*] Please create a .env file containing 'GITHUB_TOKEN=your_token' in the project directory.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Unified Jules Dispatcher & Git Push Utility")
    parser.add_argument("title", help="Title of the GitHub Issue")
    parser.add_argument("body", help="Markdown body text, path to markdown file, or '-' for stdin")
    parser.add_argument("-p", "--push", action="store_true", help="Stage, commit and push changes before creating the issue")
    parser.add_argument("-m", "--message", default="Auto-commit before dispatching task to Jules", help="Commit message to use if pushing")
    parser.add_argument("--no-push", action="store_true", help="Explicitly disable pushing even if uncommitted changes are detected")

    args = parser.parse_args()

    # 1. Handle Issue Body Input
    body_content = ""
    if args.body == "-":
        print("[*] Reading issue body from standard input...")
        body_content = sys.stdin.read()
    elif os.path.exists(args.body):
        print(f"[*] Reading issue body from file: {args.body}")
        try:
            with open(args.body, "r", encoding="utf-8") as f:
                body_content = f.read()
        except Exception as e:
            print(f"[-] Error reading file {args.body}: {e}")
            sys.exit(1)
    else:
        print("[*] Treating input body as literal text.")
        body_content = args.body

    if not body_content.strip():
        print("[-] Error: Issue body is empty.")
        sys.exit(1)

    # 2. Detect Proxy
    proxy = detect_active_proxy()
    if proxy:
        print(f"[*] Active local proxy detected: {proxy}")
    else:
        print("[*] No active local proxy detected.")

    # 3. Optional Git Stage, Commit, and Push
    if args.push and not args.no_push:
        print("=" * 60)
        print("[*] Starting Pre-dispatch Git Sync...")
        print("=" * 60)

        # Check git status
        try:
            status_output = subprocess.check_output(["git", "status", "--porcelain"]).decode().strip()
        except subprocess.CalledProcessError:
            print("[-] Error: Not a git repository or git is not installed.")
            sys.exit(1)

        branch = get_current_branch()
        print(f"[*] Current branch: {branch}")

        if status_output:
            print("[*] Detected uncommitted changes:")
            print(status_output)
            print("[*] Staging all files...")
            run_git_command(["git", "add", "-A"])
            print(f"[*] Committing changes with message: \"{args.message}\"...")
            commit_ok = run_git_command(["git", "commit", "-m", args.message])
            if not commit_ok:
                print("[-] Warning: Git commit failed. Proceeding to push anyway.")
        else:
            print("[*] Working tree is clean. Proceeding directly to push.")

        remote_url = f"https://{TOKEN}@github.com/{REPO}.git"
        push_ok = run_git_push(proxy, remote_url, branch)
        if not push_ok:
            print("[-] Error: Git push failed. Jules will not see your local modifications!")
            sys.exit(1)
        print("=" * 60)

    # 4. Prepare payload & headers for API
    payload = {
        "title": args.title,
        "body": body_content,
        "labels": ["jules"]
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "Antigravity-Jules-Dispatcher"
    }

    print("=" * 60)
    print(f"[*] Dispatching task to Google Labs Jules on {REPO}...")
    print(f"[*] Title: {args.title}")
    print("=" * 60)

    # Route A: Direct
    print("[*] Route A: Attempting direct connection to GitHub API...")
    try:
        r = requests.post(URL, json=payload, headers=headers, proxies={"http": None, "https": None}, timeout=15)
        if r.status_code in [200, 201]:
            print(f"[+] Success! Issue created directly: {r.json().get('html_url')}")
            sys.exit(0)
        else:
            print(f"[-] Route A failed with status code {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[-] Route A error: {e}")

    # Route B: Detected Proxy
    if proxy:
        print(f"[*] Route B: Attempting proxy connection via {proxy}...")
        proxy_dict = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        try:
            r = requests.post(URL, json=payload, headers=headers, proxies=proxy_dict, timeout=15, verify=False)
            if r.status_code in [200, 201]:
                print(f"[+] Success! Issue created via proxy: {r.json().get('html_url')}")
                sys.exit(0)
            else:
                print(f"[-] Route B failed with status code {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[-] Route B error: {e}")

    # Route C: Try other common local proxies
    common_proxies = ["127.0.0.1:7897", "127.0.0.1:7890", "127.0.0.1:10809", "127.0.0.1:1080"]
    for p in common_proxies:
        if p != proxy:
            print(f"[*] Route C: Attempting proxy fallback via http://{p}...")
            proxy_dict = {"http": f"http://{p}", "https": f"http://{p}"}
            try:
                r = requests.post(URL, json=payload, headers=headers, proxies=proxy_dict, timeout=8, verify=False)
                if r.status_code in [200, 201]:
                    print(f"[+] Success! Issue created via fallback proxy: {r.json().get('html_url')}")
                    sys.exit(0)
            except Exception:
                pass

    print("[-] Error: Failed to create GitHub issue under all connection routes.")
    sys.exit(1)

if __name__ == "__main__":
    main()
