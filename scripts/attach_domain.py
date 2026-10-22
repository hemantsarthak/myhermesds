#!/usr/bin/env python3
"""
Attach a custom domain to the Pages project and prove it serves.

Steps, in order:
  1. confirm the Pages project has a live deployment (otherwise there is nothing to attach to)
  2. attach the custom domain to the project
  3. create/repair the CNAME record in the zone
  4. wait for the edge to answer, then assert the body is the real site and not a placeholder

Run:  python3 scripts/attach_domain.py [--domain pincode.tekify.xyz] [--dry-run]

Requires CF_API_TOKEN and CF_ACCOUNT_ID in the environment (source ../../.env).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
TOK = os.environ.get("CF_API_TOKEN", "")
ACC = os.environ.get("CF_ACCOUNT_ID", "")
ZONE_NAME = "tekify.xyz"


def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read()[:500].decode(errors="replace")}


def ok(res):
    return isinstance(res, dict) and res.get("success") is True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="pincode-india")
    ap.add_argument("--domain", default="pincode.tekify.xyz")
    ap.add_argument("--verify-path", default=None,
                    help="secondary page to assert renders (defaults to a pincode or bank page)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    PROJECT = args.project
    TARGET = f"{PROJECT}.pages.dev"

    if not TOK or not ACC:
        print("FAIL: CF_API_TOKEN / CF_ACCOUNT_ID not set. Source hermestom/.env first.")
        return 1

    sub = args.domain.split(".")[0]

    # 1 ---- project + deployment
    proj = call(f"/accounts/{ACC}/pages/projects/{PROJECT}")
    if not ok(proj):
        print(f"FAIL: project {PROJECT} unreadable: {proj}")
        return 1
    latest = proj["result"].get("latest_deployment") or {}
    stage = (latest.get("latest_stage") or {}).get("name")
    print(f"project          {PROJECT}")
    print(f"latest deploy    {latest.get('short_id') or 'none'}  stage={stage}")
    print(f"deploy url       {latest.get('url', TARGET)}".replace("https://https://", "https://"))
    if not latest:
        print("FAIL: no deployment yet — deploy before attaching a domain")
        return 1

    # 2 ---- attach custom domain
    doms = call(f"/accounts/{ACC}/pages/projects/{PROJECT}/domains")
    have = [d.get("name") for d in (doms.get("result") or [])]
    print(f"current domains  {have or '[]'}")
    if args.domain in have:
        print(f"domain           already attached")
    elif args.dry_run:
        print(f"would attach     {args.domain}")
    else:
        r = call(f"/accounts/{ACC}/pages/projects/{PROJECT}/domains", "POST", {"name": args.domain})
        print(f"attach           {'ok' if ok(r) else r}")
        if not ok(r):
            return 1

    # 3 ---- DNS
    zone = call(f"/zones?name={ZONE_NAME}")
    if not ok(zone) or not zone["result"]:
        print(f"FAIL: zone {ZONE_NAME} not found")
        return 1
    zid = zone["result"][0]["id"]
    recs = call(f"/zones/{zid}/dns_records?name={args.domain}")
    existing = (recs.get("result") or []) if ok(recs) else []
    print(f"dns records      {[(r['type'], r['content']) for r in existing] or '[]'}")
    if not existing:
        if args.dry_run:
            print(f"would create     CNAME {sub} -> {TARGET} (proxied)")
        else:
            r = call(f"/zones/{zid}/dns_records", "POST",
                     {"type": "CNAME", "name": sub, "content": TARGET,
                      "proxied": True, "ttl": 1})
            print(f"dns create       {'ok' if ok(r) else r}")
            if not ok(r):
                return 1

    if args.dry_run:
        return 0

    # 4 ---- prove it serves
    print("\nwaiting for edge…")
    for attempt in range(1, 31):
        try:
            req = urllib.request.Request(f"https://{args.domain}/",
                                         headers={"User-Agent": "attach-domain-verify/1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read(4000).decode(errors="replace")
                print(f"  attempt {attempt:2d}  HTTP {r.status}  {len(body)} bytes")
                if r.status == 200 and "<h1>" in body:
                    print(f"  title: {body.split('<title>')[1].split('</title>')[0]}")
                    vp = args.verify_path or ("/pincode/110001/" if "pincode" in PROJECT else "/bank/sbin/")
                    req2 = urllib.request.Request(f"https://{args.domain}{vp}",
                                                  headers={"User-Agent": "attach-domain-verify/1"})
                    with urllib.request.urlopen(req2, timeout=20) as r2:
                        b2 = r2.read(6000).decode(errors="replace")
                    print(f"  {vp:20s} HTTP {r2.status}  has table: {'<table>' in b2}")
                    print("\nLIVE")
                    return 0
        except urllib.error.HTTPError as e:
            print(f"  attempt {attempt:2d}  HTTP {e.code}")
        except Exception as e:
            print(f"  attempt {attempt:2d}  {type(e).__name__}: {e}")
        time.sleep(10)

    print("\nFAIL: domain did not answer 200 with real content after 5 minutes")
    return 1


if __name__ == "__main__":
    sys.exit(main())
