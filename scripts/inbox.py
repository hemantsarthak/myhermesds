#!/usr/bin/env python3
"""
Disposable inbox over the mail.tm API, for autonomous signups.

Ad networks want an email address and send a verification link. This creates the
address, polls for the mail, and prints the verification URL so a signup can be
completed without the operator acting as mailman.

    python3 scripts/inbox.py new  [--label adsterra]
    python3 scripts/inbox.py poll <address> [minutes]
    python3 scripts/inbox.py wait <address> <substring> [minutes]
    python3 scripts/inbox.py read <address> <message-id>

State lives in .tmp/inbox.json (gitignored). Passwords never go to stdout.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import secrets
import string
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.mail.tm"
ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / ".tmp" / "inbox.json"


def api(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read()[:300].decode(errors="replace")}


def load():
    if STORE.exists():
        return json.loads(STORE.read_text())
    return {}


def save(state):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(state, indent=1))


def login(address, password):
    r = api("POST", "/token", {"address": address, "password": password})
    if "token" not in r:
        raise SystemExit(f"login failed: {r}")
    return r["token"]


def cmd_new(label):
    doms = api("GET", "/domains")
    # the API returns either a hydra envelope or a bare list depending on endpoint state
    if isinstance(doms, list):
        members = doms
    elif isinstance(doms, dict):
        members = doms.get("hydra:member") or doms.get("member") or []
    else:
        members = []
    if not members:
        raise SystemExit(f"no domains available: {doms}")
    domain = members[0]["domain"] if isinstance(members[0], dict) else members[0]

    local = (label or "ads") + "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(7))
    address = f"{local}@{domain}"
    password = "Mx9!" + "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(14))

    acc = api("POST", "/accounts", {"address": address, "password": password})
    if "_error" in acc:
        raise SystemExit(f"account create failed: {acc}")

    state = load()
    state[address] = {"password": password, "label": label, "created": int(time.time())}
    save(state)
    print(address)


def _messages(token):
    r = api("GET", "/messages?page=1", token=token)
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("hydra:member") or r.get("member") or []
    return []


def cmd_poll(address, minutes):
    state = load()
    if address not in state:
        raise SystemExit(f"unknown address {address}")
    token = login(address, state[address]["password"])
    deadline = time.time() + minutes * 60
    seen = set()
    while True:
        for m in _messages(token):
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            frm = (m.get("from") or {}).get("address", "?")
            print(f"{m['id']}\t{frm}\t{m.get('subject','')[:90]}")
        if time.time() > deadline:
            return
        time.sleep(10)


def _body(msg_id, token):
    m = api("GET", f"/messages/{msg_id}", token=token)
    parts = []
    for t in ("text", "html"):
        if m.get(t):
            parts.append(m[t])
    for arr in m.get("html") or []:
        parts.append(str(arr))
    raw = "\n".join(str(p) for p in parts)
    links = re.findall(r'https?://[^\s"\'<>)\]]+', raw)
    return m, raw, links


def cmd_wait(address, needle, minutes):
    state = load()
    if address not in state:
        raise SystemExit(f"unknown address {address}")
    token = login(address, state[address]["password"])
    deadline = time.time() + minutes * 60
    checked = set()
    while time.time() < deadline:
        for m in _messages(token):
            if m["id"] in checked:
                continue
            checked.add(m["id"])
            _, raw, links = _body(m["id"], token)
            hay = (m.get("subject", "") + " " + raw).lower()
            if needle.lower() in hay:
                print(f"MATCH  {m.get('subject','')}")
                print(f"FROM   {(m.get('from') or {}).get('address','?')}")
                for l in links[:12]:
                    print(f"LINK   {l}")
                return
        time.sleep(10)
    print("TIMEOUT — no matching mail")


def cmd_read(address, msg_id):
    state = load()
    token = login(address, state[address]["password"])
    m, raw, links = _body(msg_id, token)
    print(f"SUBJECT {m.get('subject','')}")
    print(f"FROM    {(m.get('from') or {}).get('address','?')}")
    print("---")
    print(re.sub(r"<[^>]+>", " ", raw)[:3000])
    print("--- links ---")
    for l in links[:15]:
        print(l)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new");  p.add_argument("--label", default="ads")
    p = sub.add_parser("poll"); p.add_argument("address"); p.add_argument("minutes", type=float, nargs="?", default=3)
    p = sub.add_parser("wait"); p.add_argument("address"); p.add_argument("needle"); p.add_argument("minutes", type=float, nargs="?", default=5)
    p = sub.add_parser("read"); p.add_argument("address"); p.add_argument("msg_id")
    a = ap.parse_args()
    if a.cmd == "new":
        cmd_new(a.label)
    elif a.cmd == "poll":
        cmd_poll(a.address, a.minutes)
    elif a.cmd == "wait":
        cmd_wait(a.address, a.needle, a.minutes)
    elif a.cmd == "read":
        cmd_read(a.address, a.msg_id)


if __name__ == "__main__":
    main()
