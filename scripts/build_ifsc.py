#!/usr/bin/env python3
"""
Build ifsc.tekify.xyz — a bank/branch index over the Razorpay IFSC dataset (MIT).

Input : data-source/IFSC.csv  (183,214 rows, 16 columns)
Output: site-ifsc/

Design decisions and why
------------------------
* 183,214 branches cannot get one page each: Cloudflare Pages Free allows 20,000
  files, and 183k near-duplicate generated pages on a cold domain is precisely the
  scaled-content pattern that gets a site deindexed. So the site is organised the
  other way round: 260 bank pages and 42 state pages carry the unique content, and
  exact-IFSC lookup is served client-side from per-bank JSON.
* Lookup is prefix-routed. Typing "SBIN0001234" fetches /data/bank/SBIN.json only,
  so the browser never downloads 183k records to answer one query.
* The source's DISTRICT column has 42,421 distinct state-district pairs (it is
  effectively branch-level), so there are no district pages.
"""
import argparse
import collections
import csv
import datetime
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data-source" / "IFSC.csv"
OUT = ROOT / "site-ifsc"
SITE = "https://ifsc.tekify.xyz"
BRAND = "IFSC India"
SOURCE_REPO = "razorpay/ifsc"


def ensure_dataset():
    """Fetch IFSC.csv from the upstream release if it is not already local.

    The CSV is 35 MB, so it is gitignored and pulled on demand instead of being
    committed — the build stays reproducible without bloating repository history.
    """
    if DATA.exists() and DATA.stat().st_size > 1_000_000:
        return
    import urllib.request
    DATA.parent.mkdir(parents=True, exist_ok=True)
    api = f"https://api.github.com/repos/{SOURCE_REPO}/releases/latest"
    with urllib.request.urlopen(api, timeout=60) as r:
        rel = json.loads(r.read())
    url = next(a["browser_download_url"] for a in rel["assets"] if a["name"] == "IFSC.csv")
    print(f"fetching {rel['tag_name']} IFSC.csv …")
    urllib.request.urlretrieve(url, DATA)
    print(f"  {DATA.stat().st_size/1e6:.1f} MB")

CSS = """
:root{--bg:#f8f9fb;--fg:#14171c;--mut:#5a6473;--line:#e2e6ec;--acc:#123f7c;--card:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
header{border-bottom:1px solid var(--line);background:var(--card)}
.wrap{max-width:860px;margin:0 auto;padding:0 20px}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:60px}
.brand{font-weight:700;font-size:17px;letter-spacing:-.01em}
nav a{color:var(--mut);font-size:14px;margin-left:18px}
h1{font-size:29px;line-height:1.25;letter-spacing:-.02em;margin:34px 0 10px}
h2{font-size:19px;margin:32px 0 12px;letter-spacing:-.01em}
p{color:#2b3038;margin:0 0 14px}
.lede{color:var(--mut);font-size:17px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:18px 0}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);font-weight:600}
tbody tr:last-child td{border-bottom:none}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums}
input[type=search]{width:100%;padding:14px 16px;font-size:17px;border:1px solid var(--line);
 border-radius:10px;background:var(--card);color:var(--fg);outline:none;
 font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
input[type=search]:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(18,63,124,.12)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px}
.grid a{padding:10px 12px;background:var(--card);border:1px solid var(--line);border-radius:8px;
 font-size:14px;color:var(--fg)}
.grid a:hover{border-color:var(--acc);text-decoration:none}
.crumbs{font-size:13px;color:var(--mut);margin-top:22px}
.crumbs a{color:var(--mut)}
.badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:99px;
 background:#eef2f8;color:var(--acc);margin-right:6px}
footer{border-top:1px solid var(--line);margin-top:56px;padding:26px 0 40px;color:var(--mut);
 font-size:13px;background:var(--card)}
footer a{color:var(--mut);margin-right:16px}
.adslot{min-height:0;margin:28px 0;text-align:center}
@media(max-width:560px){h1{font-size:24px}.wrap{padding:0 16px}}
"""


def page(title, desc, body, canonical, crumbs=None, jsonld=None):
    crumb = ""
    if crumbs:
        parts = ['<a href="/">Home</a>'] + [
            (f'<a href="{u}">{html.escape(t)}</a>' if u else html.escape(t)) for t, u in crumbs]
        crumb = '<div class="crumbs">' + " &rsaquo; ".join(parts) + "</div>"
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<style>{CSS}</style>
{ld}
</head>
<body>
<header><div class="wrap">
  <a class="brand" href="/">{BRAND}</a>
  <nav><a href="/bank/">Banks</a><a href="/state/">States</a><a href="/about/">About</a></nav>
</div></header>
<main class="wrap">
{crumb}
{body}
<div class="adslot" id="ad-slot-1"></div>
</main>
<footer><div class="wrap">
  <a href="/about/">About</a><a href="/privacy/">Privacy</a><a href="/contact/">Contact</a>
  <p style="margin-top:14px">IFSC and branch data from the open Razorpay IFSC dataset (MIT).
  {BRAND}, {datetime.date.today().year}.</p>
</div></footer>
</body>
</html>"""


def write(path, content):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def yes(v):
    return (v or "").strip().lower() in ("true", "1", "yes")


def build(args):
    ensure_dataset()
    rows = list(csv.DictReader(DATA.open(encoding="utf-8", errors="replace")))
    recs = []
    for r in rows:
        code = (r.get("IFSC") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", code):
            continue
        recs.append({
            "ifsc": code, "pre": code[:4],
            "bank": (r.get("BANK") or "").strip(),
            "branch": (r.get("BRANCH") or "").strip(),
            "centre": (r.get("CENTRE") or "").strip(),
            "city": (r.get("CITY") or "").strip(),
            "district": (r.get("DISTRICT") or "").strip(),
            "state": (r.get("STATE") or "").strip(),
            "address": (r.get("ADDRESS") or "").strip(),
            "micr": (r.get("MICR") or "").strip(),
            "swift": (r.get("SWIFT") or "").strip(),
            "upi": yes(r.get("UPI")), "neft": yes(r.get("NEFT")),
            "rtgs": yes(r.get("RTGS")), "imps": yes(r.get("IMPS")),
        })

    by_prefix = collections.defaultdict(list)
    by_state = collections.defaultdict(list)
    for r in recs:
        by_prefix[r["pre"]].append(r)
        if r["state"]:
            by_state[r["state"]].append(r)

    # bank name per prefix: most common non-empty BANK value (1,035 rows have it blank)
    names = {}
    for pre, rs in by_prefix.items():
        c = collections.Counter(r["bank"] for r in rs if r["bank"])
        names[pre] = c.most_common(1)[0][0] if c else pre

    # title-case shouty source labels ("MAHARASHTRA" -> "Maharashtra")
    def nice(s):
        return " ".join(w.capitalize() if w.isupper() else w for w in s.split())

    files = []

    # ---- home
    total = len(recs)
    body = f"""
<h1>Find any Indian bank branch by IFSC</h1>
<p class="lede">Look up {total:,} IFSC codes across {len(by_prefix)} banks and
{len(by_state)} states. Type an IFSC code to see the branch, or search a bank name.</p>
<input type="search" id="q" placeholder="SBIN0001234 or State Bank of India" autocomplete="off" autofocus>
<div id="res"></div>
<h2>Banks by branch count</h2>
<div class="grid">
{"".join(f'<a href="/bank/{p.lower()}/">{html.escape(names[p])} <span style="color:#8b93a1">{len(by_prefix[p]):,}</span></a>' for p in sorted(by_prefix, key=lambda x: -len(by_prefix[x]))[:24])}
</div>
<h2>What an IFSC code contains</h2>
<p>The first four characters identify the bank, the fifth is always <code>0</code>, and the
last six identify the branch. That structure is why <code>SBIN0001234</code> resolves to a
single branch of one bank: <code>SBIN</code> is State Bank of India, and <code>001234</code>
is the branch. This site keeps that mapping searchable, along with whether a branch
supports NEFT, RTGS, IMPS and UPI.</p>
"""
    files.append(write("index.html", page(
        "IFSC Code Search — Find Any Indian Bank Branch",
        f"Search {total:,} IFSC codes across {len(by_prefix)} Indian banks. Branch name, address, "
        "MICR, and whether the branch supports NEFT, RTGS, IMPS and UPI.",
        body, SITE + "/")))

    # ---- per-bank, per-shard payloads (client-side exact lookup)
    # Sharded on the LAST character, not a middle one: Indian IFSC branch codes are
    # sequential, so SBIN0000001..SBIN0026498 share their middle characters and all
    # land in one shard. The last digit varies uniformly, so this keeps shards small
    # regardless of how a bank numbers its branches.
    for pre, rs in by_prefix.items():
        shards = collections.defaultdict(list)
        for r in rs:
            shards[r["ifsc"][-1]].append(r)
        for ch, sh in shards.items():
            payload = [[r["ifsc"], r["branch"], r["address"], r["city"] or r["centre"],
                        r["district"], r["state"], r["micr"], r["swift"],
                        int(r["upi"]), int(r["neft"]), int(r["rtgs"]), int(r["imps"])]
                       for r in sh]
            files.append(write(f"data/bank/{pre}/{ch}.json",
                               json.dumps(payload, separators=(",", ":"), ensure_ascii=False)))
        # code-only index for prefix suggestions: far smaller than full records
        files.append(write(f"data/codes/{pre}.json",
                           json.dumps(sorted(r["ifsc"] for r in rs),
                                      separators=(",", ":"))))

    # ---- bank index + state index payloads
    files.append(write("data/banks.json", json.dumps(
        {p: [names[p], len(by_prefix[p])] for p in by_prefix},
        separators=(",", ":"), ensure_ascii=False)))

    search_js = """
(function(){
  var banks=null, cache={}, q=document.getElementById('q'), res=document.getElementById('res');
  function esc(s){return String(s).replace(/[&<>]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function loadBanks(){ if(banks) return Promise.resolve(banks);
    return fetch('/data/banks.json').then(function(r){return r.json()})
      .then(function(d){banks=d;return d}); }
  function loadBank(pre, sh){ var k=pre+sh; if(cache[k]) return Promise.resolve(cache[k]);
    return fetch('/data/bank/'+pre+'/'+sh+'.json').then(function(r){return r.json()})
      .then(function(d){cache[k]=d;return d}).catch(function(){return []}); }
  function row(r){
    var f=[['NEFT',r[9]],['RTGS',r[10]],['IMPS',r[11]],['UPI',r[8]]]
      .filter(function(x){return x[1]}).map(function(x){return '<span class="badge">'+x[0]+'</span>'}).join('');
    return '<div class="card"><h2 style="margin-top:0" class="mono">'+r[0]+'</h2>'+
      '<p style="margin-bottom:8px"><b>'+esc(r[1])+'</b><br>'+
      esc(r[2])+'<br>'+esc(r[4])+', '+esc(r[5])+'</p>'+
      '<p style="margin-bottom:0;font-size:14px">'+f+
      (r[6]?'<br>MICR <span class="mono">'+esc(r[6])+'</span>':'')+
      (r[7]?'<br>SWIFT <span class="mono">'+esc(r[7])+'</span>':'')+'</p></div>';
  }
  function run(){
    var t=q.value.trim().toUpperCase();
    if(t.length<4){res.innerHTML='';return;}
    if(/^[A-Z]{4}$/.test(t)){
      loadBanks().then(function(b){
        var hits=Object.keys(b).filter(function(p){return p===t||b[p][0].toUpperCase().indexOf(t)>-1});
        res.innerHTML=hits.slice(0,20).map(function(p){
          return '<a class="grid" style="display:block;margin:6px 0;padding:10px 12px;background:#fff;'+
            'border:1px solid #e2e6ec;border-radius:8px" href="/bank/'+p.toLowerCase()+'/">'+
            esc(b[p][0])+' <span style="color:#8b93a1">'+b[p][1].toLocaleString()+' branches</span></a>';
        }).join('')||'<div class="card">No bank matches that prefix.</div>';
      });
      return;
    }
    if(t.length>=5){
      var pre=t.slice(0,4);
      if(t.length<11){
        // partial code: use the code-only index, then let the user pick a full code
        fetch('/data/codes/'+pre+'.json').then(function(r){return r.json()}).catch(function(){return []})
          .then(function(codes){
            var part=codes.filter(function(c){return c.indexOf(t)===0}).slice(0,10);
            if(!part.length){res.innerHTML='<div class="card">No code under <span class="mono">'+esc(t)+'</span>.</div>';return;}
            res.innerHTML=part.map(function(c){
              return '<a class="grid" style="display:block;margin:6px 0;padding:10px 12px;background:#fff;'+
                'border:1px solid #e2e6ec;border-radius:8px" href="/lookup/?ifsc='+c+'">'+
                '<span class="mono">'+c+'</span></a>';
            }).join('');
          });
        return;
      }
      loadBank(pre, t[10]).then(function(rs){
        var hit=rs.filter(function(r){return r[0]===t});
        if(hit.length){res.innerHTML=row(hit[0]);return;}
        var part=rs.filter(function(r){return r[0].indexOf(t)===0}).slice(0,10);
        res.innerHTML=part.length?part.map(row).join(''):'<div class="card">No branch under <span class="mono">'+esc(t)+'</span>.</div>';
      });
    }
  }
  q.addEventListener('input',run);
  loadBanks();
  // allow /lookup/?ifsc=SBIN0001234 deep links from the suggestion list
  var deep=new URLSearchParams(location.search).get('ifsc');
  if(deep){q.value=deep.toUpperCase();run();}
})();
"""
    files.append(write("assets/search.js", search_js))
    hp = OUT / "index.html"
    hp.write_text(hp.read_text(encoding="utf-8").replace(
        "</main>", '<script src="/assets/search.js" defer></script>\n</main>'), encoding="utf-8")

    # ---- bank index page
    order = sorted(by_prefix, key=lambda p: names[p].lower())
    grid = "".join(f'<a href="/bank/{p.lower()}/">{html.escape(names[p])} '
                   f'<span style="color:#8b93a1">{len(by_prefix[p]):,}</span></a>' for p in order)
    files.append(write("bank/index.html", page(
        "All Banks — IFSC Codes by Bank",
        f"Every Indian bank with an IFSC prefix: {len(by_prefix)} banks and {total:,} branches.",
        f"<h1>Banks</h1><p class='lede'>{len(by_prefix)} banks, {total:,} branches.</p>"
        f"<div class='grid'>{grid}</div>",
        SITE + "/bank/", [("Banks", None)])))

    # ---- individual bank pages
    for pre, rs in by_prefix.items():
        nm = names[pre]
        states = collections.Counter(r["state"] for r in rs if r["state"])
        feats = {k: sum(1 for r in rs if r[k]) for k in ("neft", "rtgs", "imps", "upi")}
        micr = sum(1 for r in rs if r["micr"])
        swift = sum(1 for r in rs if r["swift"])
        sample = sorted(rs, key=lambda r: r["ifsc"])[:15]
        rows = "".join(
            f'<tr><td class="mono">{r["ifsc"]}</td><td>{html.escape(r["branch"])}</td>'
            f'<td>{html.escape(nice(r["district"]))}</td><td>{html.escape(nice(r["state"]))}</td></tr>'
            for r in sample)
        st = "".join(f'<a href="/state/{slug(s)}/">{html.escape(nice(s))} '
                     f'<span style="color:#8b93a1">{c:,}</span></a>'
                     for s, c in states.most_common(12))
        body = (f"<h1>{html.escape(nm)} IFSC codes</h1>"
                f"<p class='lede'>{len(rs):,} branches across {len(states)} states and "
                f"union territories. IFSC prefix <span class='mono'>{pre}</span>.</p>"
                f"<div class='card'><table><tbody>"
                f"<tr><th>IFSC prefix</th><td class='mono'>{pre}</td></tr>"
                f"<tr><th>Branches</th><td>{len(rs):,}</td></tr>"
                f"<tr><th>States covered</th><td>{len(states)}</td></tr>"
                f"<tr><th>MICR codes</th><td>{micr:,}</td></tr>"
                f"<tr><th>SWIFT codes</th><td>{swift:,}</td></tr>"
                f"<tr><th>NEFT / RTGS / IMPS / UPI</th><td>{feats['neft']:,} / "
                f"{feats['rtgs']:,} / {feats['imps']:,} / {feats['upi']:,}</td></tr>"
                f"</tbody></table></div>"
                f"<h2>Where {html.escape(nm)} has branches</h2><div class='grid'>{st}</div>"
                f"<h2>First branches by IFSC</h2>"
                f"<div class='card'><table><thead><tr><th>IFSC</th><th>Branch</th>"
                f"<th>District</th><th>State</th></tr></thead><tbody>{rows}</tbody></table></div>")
        files.append(write(f"bank/{pre.lower()}/index.html", page(
            f"{nm} IFSC Codes — {len(rs):,} Branches, Prefix {pre}",
            f"All {len(rs):,} {nm} branches by IFSC code, with district, state, MICR and "
            f"NEFT/RTGS/IMPS/UPI support. IFSC prefix {pre}.",
            body, f"{SITE}/bank/{pre.lower()}/", [("Banks", "/bank/"), (nm, None)],
            {"@context": "https://schema.org", "@type": "BankOrCreditUnion", "name": nm})))

    # ---- state index + pages
    sgrid = "".join(f'<a href="/state/{slug(s)}/">{html.escape(nice(s))} '
                    f'<span style="color:#8b93a1">{len(rs):,}</span></a>'
                    for s, rs in sorted(by_state.items(), key=lambda kv: -len(kv[1])))
    files.append(write("state/index.html", page(
        "IFSC Codes by State",
        f"Browse {total:,} IFSC codes across {len(by_state)} Indian states and union territories.",
        f"<h1>States</h1><p class='lede'>{total:,} branches across {len(by_state)} states.</p>"
        f"<div class='grid'>{sgrid}</div>",
        SITE + "/state/", [("States", None)])))

    for st_name, rs in by_state.items():
        banks = collections.Counter(r["pre"] for r in rs)
        g = "".join(f'<a href="/bank/{p.lower()}/">{html.escape(names[p])} '
                    f'<span style="color:#8b93a1">{c:,}</span></a>'
                    for p, c in banks.most_common(30))
        body = (f"<h1>{html.escape(nice(st_name))} IFSC codes</h1>"
                f"<p class='lede'>{len(rs):,} bank branches across {len(banks)} banks in "
                f"{html.escape(nice(st_name))}.</p>"
                f"<h2>Banks in {html.escape(nice(st_name))}</h2><div class='grid'>{g}</div>")
        files.append(write(f"state/{slug(st_name)}/index.html", page(
            f"{nice(st_name)} IFSC Codes — {len(rs):,} Branches",
            f"All {len(rs):,} bank branches in {nice(st_name)} by IFSC code, across {len(banks)} banks.",
            body, f"{SITE}/state/{slug(st_name)}/", [("States", "/state/"), (nice(st_name), None)])))

    # ---- lookup route
    files.append(write("lookup/index.html", page(
        "IFSC Lookup — Branch Details for Any Code",
        "Enter an IFSC code to see the bank, branch, address, MICR and supported payment rails.",
        """<h1>IFSC lookup</h1>
<p class="lede">Enter an eleven-character IFSC code.</p>
<input type="search" id="q" placeholder="SBIN0001234" autocomplete="off">
<div id="res"></div>""",
        SITE + "/lookup/", [("Lookup", None)])))
    lp = OUT / "lookup" / "index.html"
    lp.write_text(lp.read_text(encoding="utf-8").replace(
        "</main>", '<script src="/assets/search.js" defer></script>\n</main>'), encoding="utf-8")

    # ---- static pages
    files.append(write("about/index.html", page(
        "About IFSC India", "What an IFSC code is, where this data comes from, and its licence.",
        f"""<h1>About</h1>
<p>IFSC India indexes {total:,} Indian bank branches across {len(by_prefix)} banks by their
IFSC code, the eleven-character identifier used for NEFT, RTGS and IMPS transfers.</p>
<h2>How the code works</h2>
<p>The first four characters are the bank, the fifth is always zero, and the last six are
the branch. <span class="mono">SBIN0001234</span> is therefore State Bank of India, branch
001234.</p>
<h2>Data</h2>
<p>Branch records come from the open Razorpay IFSC dataset, published under the MIT licence
and refreshed from the RBI's published branch lists. Each record carries the bank, branch
name, address, city, district, state, MICR code where one exists, SWIFT code for branches
that have one, and whether the branch supports NEFT, RTGS, IMPS and UPI.</p>
<h2>Limits</h2>
<p>This is not an official bank or RBI service. Confirm payment details against the bank's
own records before transferring money &mdash; IFSC directories go stale when branches merge
or close, and a wrong code routes funds to the wrong account.</p>""",
        SITE + "/about/", [("About", None)])))

    files.append(write("privacy/index.html", page(
        "Privacy Policy", "What this site collects and how advertising is handled.",
        """<h1>Privacy policy</h1>
<p>This is a static site. There are no accounts, no forms that submit anywhere, and no
storage of what you type &mdash; IFSC lookups run in your browser against a data file.</p>
<h2>Advertising</h2>
<p>Pages may carry third-party advertising. Ad vendors may use cookies to serve ads based on
prior visits to this and other sites. You can opt out through your browser settings or the
vendor's own controls.</p>
<h2>Server logs</h2>
<p>The site is delivered by a content delivery network that processes standard request
metadata (IP address, user agent, URL) to serve pages and block abuse.</p>""",
        SITE + "/privacy/", [("Privacy", None)])))

    files.append(write("contact/index.html", page(
        "Contact — Report an Incorrect IFSC Record",
        "Report a wrong branch, a closed branch, or a missing IFSC code.",
        """<h1>Contact</h1>
<p>Send corrections to <b>hello&#64;tekify.xyz</b>, including the IFSC code and what is wrong.</p>
<p>Corrections are applied to the source dataset and republished, so a fix lands everywhere
the record appears.</p>""",
        SITE + "/contact/", [("Contact", None)])))

    files.append(write("404.html", page(
        "Page not found", "That page does not exist.",
        """<h1>Not found</h1><p>Try the <a href="/">IFSC search</a> or browse
<a href="/bank/">banks</a>.</p>""", SITE + "/404.html")))

    # ---- robots + sitemap
    files.append(write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n"))
    urls = []
    for f in files:
        rel = f.relative_to(OUT).as_posix()
        if rel == "index.html":
            urls.append("/")
        elif rel.endswith("/index.html"):
            urls.append("/" + rel[: -len("index.html")])
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    today = datetime.date.today().isoformat()
    for u in sorted(set(urls)):
        sm.append(f"<url><loc>{SITE}{u}</loc><lastmod>{today}</lastmod>"
                  f"<priority>{'1.0' if u == '/' else '0.6'}</priority></url>")
    sm.append("</urlset>")
    files.append(write("sitemap.xml", "\n".join(sm)))

    files.append(write("_headers", """/data/*
  Cache-Control: public, max-age=86400
/assets/*
  Cache-Control: public, max-age=604800
/*.html
  Cache-Control: public, max-age=3600
"""))

    print(f"branches      {len(recs):,}")
    print(f"banks         {len(by_prefix)}")
    print(f"states        {len(by_state)}")
    print(f"files written {len(files):,}")
    print(f"site size     {sum(f.stat().st_size for f in files)/1e6:.1f} MB")
    big = max(files, key=lambda f: f.stat().st_size)
    print(f"largest file  {big.relative_to(OUT).as_posix()} {big.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    build(ap.parse_args())
