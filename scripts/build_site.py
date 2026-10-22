#!/usr/bin/env python3
"""
Build the pincode.tekify site: static HTML from the local India post-office dataset.

Input : ../indiapicodedata.json  (39,732 raw records, utf-8-sig / BOM)
Output: site/  (static, deployable to Cloudflare Pages)

Design notes
------------
* No framework, no build step, no external requests. Every page is one self-contained
  HTML file with inline CSS. That keeps the site fast on Indian mobile networks and
  means zero dependency drift over the life of the project.
* The full dataset is also shipped as data/pincodes.json so the homepage can search
  all 38,936 records client-side. Cloudflare Brotli-compresses it at the edge
  (2.3 MB raw -> ~330 KB on the wire), so the search box costs one lazy fetch.
* Page budget: Cloudflare Pages Free allows 20,000 files per site. We generate
  states + districts + the top N pincodes by post-office density, and keep the
  rest reachable through client-side search. Raise --pincode-limit as indexing proves out.
"""
import json
import re
import html
import argparse
import pathlib
import datetime
import collections

import ads

ROOT = pathlib.Path(__file__).resolve().parent.parent          # .../moneyds
DATA = ROOT / "data-source" / "indiapicodedata.json"           # copied in; project is self-contained
OUT = ROOT / "site"
SITE = "https://pincode.tekify.xyz"
BRAND = "Pincode India"

# ----------------------------------------------------------------------------- data

def load_records():
    """Parse the raw dump into clean records. Government exports carry a BOM."""
    raw = json.loads(DATA.read_text(encoding="utf-8-sig"))
    seen, out = set(), []
    for r in raw:
        pc = str(r.get("Pincode", "")).strip()
        po = str(r.get("PostOfficeName", "")).strip()
        if not re.fullmatch(r"\d{6}", pc):          # one 5-digit row in the source data
            continue
        key = (pc, po)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "pc": pc,
            "po": po,
            "ci": str(r.get("City", "")).strip(),
            "di": str(r.get("District", "")).strip(),
            "st": str(r.get("State", "")).strip(),
        })

    # Canonicalise label casing. The source contains both "Bishenpur" and "BISHENPUR"
    # for one district, and the same pattern elsewhere; without this they slug to the
    # same URL and one set of pages silently overwrites the other.
    def canonical(field):
        counts = collections.defaultdict(collections.Counter)
        for r in out:
            if r[field]:
                counts[r[field].casefold()][r[field]] += 1
        return {
            k: sorted(c.items(), key=lambda kv: (-kv[1],
                                                 not any(ch.islower() for ch in kv[0]),
                                                 kv[0]))[0][0]
            for k, c in counts.items()
        }

    for field in ("st", "di", "ci"):
        m = canonical(field)
        for r in out:
            r[field] = m.get(r[field].casefold(), r[field])

    return out


def slug(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "x"


# ----------------------------------------------------------------------------- html shell

CSS = """
:root{--bg:#fbfaf8;--fg:#16181d;--mut:#5b6472;--line:#e3e0da;--acc:#0f5c4a;--card:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
header{border-bottom:1px solid var(--line);background:var(--card)}
.wrap{max-width:820px;margin:0 auto;padding:0 20px}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:60px}
.brand{font-weight:700;font-size:17px;letter-spacing:-.01em}
nav a{color:var(--mut);font-size:14px;margin-left:18px}
h1{font-size:30px;line-height:1.25;letter-spacing:-.02em;margin:34px 0 10px}
h2{font-size:20px;margin:34px 0 12px;letter-spacing:-.01em}
p{color:#2c3138;margin:0 0 14px}
.lede{color:var(--mut);font-size:17px;margin-bottom:26px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:18px 0}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line)}
th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);font-weight:600}
tbody tr:last-child td{border-bottom:none}
td.num{font-variant-numeric:tabular-nums;font-weight:600}
input[type=search]{width:100%;padding:14px 16px;font-size:17px;border:1px solid var(--line);
 border-radius:10px;background:var(--card);color:var(--fg);outline:none}
input[type=search]:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(15,92,74,.12)}
#res{margin-top:14px}
.hit{display:block;padding:11px 14px;border:1px solid var(--line);border-bottom:none;background:var(--card)}
.hit:first-child{border-radius:10px 10px 0 0}
.hit:last-child{border-bottom:1px solid var(--line);border-radius:0 0 10px 10px}
.hit:only-child{border-radius:10px}
.hit b{font-variant-numeric:tabular-nums}
.hit span{color:var(--mut);font-size:14px}
.crumbs{font-size:13px;color:var(--mut);margin-top:22px}
.crumbs a{color:var(--mut)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
.grid a{padding:10px 12px;background:var(--card);border:1px solid var(--line);
 border-radius:8px;font-size:14px;color:var(--fg)}
.grid a:hover{border-color:var(--acc);text-decoration:none}
footer{border-top:1px solid var(--line);margin-top:56px;padding:26px 0 40px;
 color:var(--mut);font-size:13px;background:var(--card)}
footer a{color:var(--mut);margin-right:16px}
/* Ad container: reserved height prevents layout shift when a network tag is added. */
.adslot{min-height:0;margin:28px 0;text-align:center}
@media(max-width:560px){h1{font-size:25px}.wrap{padding:0 16px}}
"""


def page(title, desc, body, canonical, crumbs=None, jsonld=None):
    """One self-contained HTML document."""
    crumb_html = ""
    if crumbs:
        parts = [f'<a href="/">Home</a>'] + [
            (f'<a href="{u}">{html.escape(t)}</a>' if u else html.escape(t)) for t, u in crumbs
        ]
        crumb_html = '<div class="crumbs">' + " &rsaquo; ".join(parts) + "</div>"
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
{ads.head()}
</head>
<body>
<header><div class="wrap">
  <a class="brand" href="/">{BRAND}</a>
  <nav><a href="/state/">States</a><a href="/about/">About</a></nav>
</div></header>
<main class="wrap">
{crumb_html}
{body}
{ads.slot()}
</main>
<footer><div class="wrap">
  <a href="/about/">About</a><a href="/privacy/">Privacy</a><a href="/contact/">Contact</a>
  <p style="margin-top:14px">Data compiled from India Post post-office listings. {BRAND}, {datetime.date.today().year}.</p>
</div></footer>
</body>
</html>"""


def write(path, content):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ----------------------------------------------------------------------------- pages

def build(args):
    recs = load_records()
    by_state = collections.defaultdict(list)
    by_district = collections.defaultdict(list)   # (state, district) -> records
    by_pincode = collections.defaultdict(list)

    for r in recs:
        if not r["st"] or not r["di"]:
            continue
        by_state[r["st"]].append(r)
        by_district[(r["st"], r["di"])].append(r)
        by_pincode[r["pc"]].append(r)

    # Which pincodes get their own page: the densest ones (urban = most searched).
    ranked = sorted(by_pincode.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    chosen = dict(ranked[: args.pincode_limit])

    files = []

    # ---- homepage
    total_po = len(recs)
    body = f"""
<h1>Find any Indian pincode</h1>
<p class="lede">Search {total_po:,} post offices across {len(by_pincode):,} pincodes,
{len(by_district):,} districts and {len(by_state)} states. Type a pincode, a post office,
a district or a state.</p>
<input type="search" id="q" placeholder="110001, Connaught Place, Khammam&hellip;" autocomplete="off" autofocus>
<div id="res"></div>
<h2>Browse by state</h2>
<div class="grid">
{"".join(f'<a href="/state/{slug(s)}/">{html.escape(s)} <span style="color:#8b93a1">{len(by_state[s]):,}</span></a>' for s in sorted(by_state))}
</div>
<h2>What this is</h2>
<p>Every Indian postal code maps to one or more post offices, and each of those sits inside a
district and a state. This site keeps that mapping searchable and readable, including the
large metro pincodes that cover dozens of individual post offices &mdash; the ones most
address forms silently flatten into a single entry.</p>
"""
    files.append(write("index.html", page(
        "India Pincode Search — Post Offices, Districts & States",
        f"Search {total_po:,} Indian post offices by pincode, post office name, district or state. "
        f"Covers {len(by_pincode):,} pincodes across {len(by_state)} states.",
        body, SITE + "/")))

    # ---- search payload
    compact = [[r["pc"], r["po"], r["ci"], r["di"], r["st"]] for r in recs]
    files.append(write("data/pincodes.json",
                       json.dumps(compact, separators=(",", ":"), ensure_ascii=False)))
    # which pincodes have a static page, so the search UI never links a 404
    files.append(write("data/pages.json",
                       json.dumps(sorted(chosen), separators=(",", ":"))))
    # district -> url map, so client-side pages can deep-link without guessing slugs
    files.append(write("data/districts.json",
                       json.dumps({f"{di}|{st}": f"/district/{slug(st)}-{slug(di)}/"
                                   for (st, di) in by_district},
                                  separators=(",", ":"), ensure_ascii=False)))

    # search client, kept separate so the homepage HTML stays cacheable
    search_js = """
(function(){
  var data=null, hasPage={}, q=document.getElementById('q'), res=document.getElementById('res');
  function load(){
    if(data) return Promise.resolve(data);
    return Promise.all([
      fetch('/data/pincodes.json').then(function(r){return r.json()}),
      fetch('/data/pages.json').then(function(r){return r.json()}).catch(function(){return []})
    ]).then(function(out){
      data=out[0];
      for(var i=0;i<out[1].length;i++) hasPage[out[1][i]]=1;
      return data;
    });
  }
  function esc(s){return s.replace(/[&<>]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function render(rows,term){
    if(!term){res.innerHTML='';return;}
    if(!rows.length){res.innerHTML='<div class="card">No match for <b>'+esc(term)+'</b>. Check the pincode is six digits.</div>';return;}
    res.innerHTML=rows.map(function(r){
      // Link the static page when one exists, otherwise the generic lookup route.
      // Linking unconditionally is what produced thousands of 404s in the first build.
      var href = hasPage[r[0]] ? '/pincode/'+r[0]+'/' : '/lookup/?pincode='+r[0];
      return '<a class="hit" href="'+href+'"><b>'+r[0]+'</b> &middot; '+esc(r[1])+
             ' <span>&mdash; '+esc(r[3])+', '+esc(r[4])+'</span></a>';
    }).join('');
  }
  q.addEventListener('input',function(){
    var term=q.value.trim().toLowerCase();
    if(term.length<2){render([],'');return;}
    load().then(function(d){
      var starts=[],has=[];
      for(var i=0;i<d.length;i++){
        var r=d[i], pc=r[0];
        if(pc.indexOf(term)===0){starts.push(r);}
        else if(has.length<20 && (r[1].toLowerCase().indexOf(term)>-1||r[3].toLowerCase().indexOf(term)>-1||r[4].toLowerCase().indexOf(term)>-1)){has.push(r);}
        if(starts.length>=20) break;
      }
      render(starts.concat(has).slice(0,20),term);
    });
  });
  // warm the payload once the page is idle so the first keystroke is instant
  if('requestIdleCallback' in window){requestIdleCallback(load,{timeout:3000});}
  else{setTimeout(load,1200);}
})();
"""
    files.append(write("assets/search.js", search_js))
    # inject the script tag into the homepage (written above without it)
    hp = OUT / "index.html"
    hp.write_text(hp.read_text(encoding="utf-8").replace(
        "</main>", '<script src="/assets/search.js" defer></script>\n</main>'), encoding="utf-8")

    # ---- state index
    rows = "".join(
        f'<tr><td><a href="/state/{slug(s)}/">{html.escape(s)}</a></td>'
        f'<td class="num">{len({d for (st, d) in by_district if st == s}):,}</td>'
        f'<td class="num">{len({r["pc"] for r in by_state[s]}):,}</td>'
        f'<td class="num">{len(by_state[s]):,}</td></tr>'
        for s in sorted(by_state))
    files.append(write("state/index.html", page(
        "Indian States — Pincodes and Post Offices",
        "All Indian states and union territories with their pincode, district and post office counts.",
        f"<h1>States and union territories</h1><p class='lede'>Pincode coverage by state.</p>"
        f"<div class='card'><table><thead><tr><th>State</th><th>Districts</th><th>Pincodes</th><th>Post offices</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>",
        SITE + "/state/", [("States", None)])))

    # ---- state pages
    for st, rs in by_state.items():
        dists = sorted({r["di"] for r in rs})
        pcs = {r["pc"] for r in rs}
        links = "".join(
            f'<a href="/district/{slug(st)}-{slug(d)}/">{html.escape(d)} '
            f'<span style="color:#8b93a1">{len([r for r in rs if r["di"]==d]):,}</span></a>'
            for d in dists)
        body = (f"<h1>{html.escape(st)} pincodes</h1>"
                f"<p class='lede'>{len(pcs):,} pincodes across {len(dists)} districts "
                f"and {len(rs):,} post offices.</p>"
                f"<h2>Districts in {html.escape(st)}</h2><div class='grid'>{links}</div>")
        files.append(write(f"state/{slug(st)}/index.html", page(
            f"{st} Pincodes — {len(pcs):,} Codes, {len(dists)} Districts",
            f"All {len(pcs):,} pincodes in {st}, organised by district. {len(rs):,} post offices listed.",
            body, f"{SITE}/state/{slug(st)}/",
            [(st, None)],
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": f"{st} pincodes", "url": f"{SITE}/state/{slug(st)}/"})))

    # ---- district pages
    for (st, di), rs in by_district.items():
        pcs = sorted({r["pc"] for r in rs})
        # Only link to pincode pages that were actually emitted; plain text otherwise.
        # Without this the district tables produce thousands of 404s on a fresh site,
        # which burns crawl budget on a brand-new domain.
        rows = "".join(
            (f'<tr><td class="num"><a href="/pincode/{r["pc"]}/">{r["pc"]}</a></td>'
             if r["pc"] in chosen else
             f'<tr><td class="num">{r["pc"]}</td>')
            + f'<td>{html.escape(r["po"])}</td><td>{html.escape(r["ci"] or di)}</td></tr>'
            for r in sorted(rs, key=lambda x: (x["pc"], x["po"])))
        body = (f"<h1>{html.escape(di)} district pincodes</h1>"
                f"<p class='lede'>{len(rs):,} post offices across {len(pcs):,} pincodes "
                f"in {html.escape(di)}, {html.escape(st)}.</p>"
                f"<div class='card'><table><thead><tr><th>Pincode</th><th>Post office</th><th>City</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div>")
        files.append(write(f"district/{slug(st)}-{slug(di)}/index.html", page(
            f"{di} Pincodes — {len(pcs):,} Codes in {st}",
            f"Complete list of {len(pcs):,} pincodes and {len(rs):,} post offices in {di} district, {st}.",
            body, f"{SITE}/district/{slug(st)}-{slug(di)}/",
            [(st, f"/state/{slug(st)}/"), (di, None)],
            {"@context": "https://schema.org", "@type": "AdministrativeArea",
             "name": f"{di}, {st}"})))

    # ---- pincode pages (top N by density)
    for pc, rs in chosen.items():
        head = rs[0]
        st, di = head["st"], head["di"]
        # neighbouring pincodes in the same district that have their own page
        sibs = sorted({r["pc"] for r in by_district[(st, di)]
                       if r["pc"] != pc and r["pc"] in chosen})[:12]
        rows = "".join(f"<tr><td>{html.escape(r['po'])}</td>"
                       f"<td>{html.escape(r['ci'] or di)}</td></tr>"
                       for r in sorted(rs, key=lambda x: x["po"]))
        sib = "".join(f'<a href="/pincode/{s}/">{s}</a>' for s in sibs)
        body = (f"<h1>Pincode {pc} &mdash; {html.escape(di)}, {html.escape(st)}</h1>"
                f"<p class='lede'>{len(rs)} post office{'s' if len(rs)!=1 else ''} "
                f"served by pincode {pc}.</p>"
                f"<div class='card'><table><thead><tr><th>Post office</th><th>City</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div>"
                + (f"<h2>Other pincodes in {html.escape(di)}</h2><div class='grid'>{sib}</div>" if sib else ""))
        files.append(write(f"pincode/{pc}/index.html", page(
            f"Pincode {pc} — {di}, {st} | {len(rs)} Post Offices",
            f"Pincode {pc} belongs to {di} district, {st}. "
            f"Post offices: {', '.join(r['po'] for r in rs[:8])}.",
            body, f"{SITE}/pincode/{pc}/",
            [(st, f"/state/{slug(st)}/"), (di, f"/district/{slug(st)}-{slug(di)}/"), (pc, None)],
            {"@context": "https://schema.org", "@type": "PostalAddress",
             "postalCode": pc, "addressRegion": st, "addressLocality": di})))

    # ---- generic lookup route: covers all 23,913 pincodes, including the 15,913
    # that do not get a pre-rendered page. Without this the search box can only
    # serve the 8,000 that do, and every other query is a dead end.
    files.append(write("lookup/index.html", page(
        "Pincode lookup — post offices, district and state",
        "Look up any Indian pincode: every post office it covers, plus the district and state.",
        """<h1>Pincode lookup</h1>
<p class="lede">Enter any six-digit pincode to see every post office it covers.</p>
<input type="search" id="q" inputmode="numeric" placeholder="e.g. 110001" autocomplete="off">
<div id="res"></div>""",
        SITE + "/lookup/", [("Lookup", None)])))

    lookup_js = """
(function(){
  var q=document.getElementById('q'), res=document.getElementById('res'), data=null, dmap=null;
  function esc(s){return String(s).replace(/[&<>]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function load(){ if(data) return Promise.resolve(data);
    return Promise.all([
      fetch('/data/pincodes.json').then(function(r){return r.json()}),
      fetch('/data/districts.json').then(function(r){return r.json()}).catch(function(){return {}})
    ]).then(function(o){data=o[0];dmap=o[1];return data;}); }
  function show(pc){
    if(!/^\\d{6}$/.test(pc)){res.innerHTML='<div class="card">A pincode is six digits.</div>';return;}
    load().then(function(d){
      var rows=d.filter(function(r){return r[0]===pc;});
      if(!rows.length){res.innerHTML='<div class="card">No post office is listed under <b>'+pc+'</b>.</div>';return;}
      var st=rows[0][4], di=rows[0][3];
      document.title='Pincode '+pc+' — '+di+', '+st;
      var body=rows.map(function(r){
        return '<tr><td>'+esc(r[1])+'</td><td>'+esc(r[2]||di)+'</td></tr>';
      }).join('');
      var du=(dmap&&dmap[di+'|'+st])||('/state/');
      res.innerHTML='<h2>Pincode '+pc+'</h2><p class="lede">'+rows.length+
        ' post office'+(rows.length!==1?'s':'')+' in '+esc(di)+', '+esc(st)+'.</p>'+
        '<div class="card"><table><thead><tr><th>Post office</th><th>City</th></tr></thead>'+
        '<tbody>'+body+'</tbody></table></div>'+
        '<p><a href="'+du+'">All pincodes in '+esc(di)+'</a></p>';
    });
  }
  q.addEventListener('input',function(){ if(q.value.trim().length===6) show(q.value.trim()); });
  var p=new URLSearchParams(location.search).get('pincode');
  if(p){q.value=p;show(p);}
})();
"""
    files.append(write("assets/lookup.js", lookup_js))
    lp = OUT / "lookup" / "index.html"
    lp.write_text(lp.read_text(encoding="utf-8").replace(
        "</main>", '<script src="/assets/lookup.js" defer></script>\n</main>'), encoding="utf-8")

    # ---- static pages required for ad-network review
    files.append(write("about/index.html", page(
        "About Pincode India", "What this site is, where the data comes from, and how it is maintained.",
        """<h1>About</h1>
<p>Pincode India is a searchable index of Indian postal codes and the post offices that
sit inside them. It exists because most address forms ask for a pincode and then throw
away the part that actually identifies where you are: which post office, which district,
which taluk.</p>
<h2>Where the data comes from</h2>
<p>The listings are compiled from India Post post-office data covering 38,936 post offices,
23,913 pincodes and 586 district records across 35 states and union territories. Each
record is a post office name, its pincode, city, district and state.</p>
<h2>How it is maintained</h2>
<p>The dataset is rebuilt and republished when the source changes. Corrections can be sent
through the <a href="/contact/">contact page</a> and are applied to the underlying data
rather than patched per page.</p>
<h2>What it is not</h2>
<p>This is not an official India Post service and it does not process mail, track
consignments, or provide postal rates. For those, use India Post directly.</p>""",
        SITE + "/about/", [("About", None)])))

    files.append(write("privacy/index.html", page(
        "Privacy Policy", "What data this site collects and how advertising is handled.",
        """<h1>Privacy policy</h1>
<p>This site is a static website. It does not have user accounts, it does not ask for
personal information, and it does not store anything you type into the search box &mdash;
searching happens entirely in your browser against a data file, so your query is never
sent to a server.</p>
<h2>Advertising</h2>
<p>Pages on this site may display third-party advertising. Ad vendors may use cookies or
similar technologies to serve ads based on your prior visits to this and other websites.
You can opt out of personalised advertising through your browser settings or the ad
vendor's own controls.</p>
<h2>Server logs</h2>
<p>The site is served by a content delivery network that processes standard request
metadata (IP address, user agent, requested URL) to deliver pages and protect against
abuse.</p>
<h2>Contact</h2>
<p>Questions about this policy: see the <a href="/contact/">contact page</a>.</p>""",
        SITE + "/privacy/", [("Privacy", None)])))

    files.append(write("contact/index.html", page(
        "Contact — Report a Pincode or Post Office Error",
        "Report a wrong pincode, a missing post office, or ask a question about the data.",
        """<h1>Contact</h1>
<p>Send corrections, missing post offices or data errors to
<b>hello&#64;tekify.xyz</b> and include the pincode and the post office name.</p>
<p>Corrections are applied to the source dataset and republished, so a fix lands on every
page that references the record rather than only the one you noticed.</p>""",
        SITE + "/contact/", [("Contact", None)])))

    files.append(write("404.html", page(
        "Page not found", "That pincode page does not exist.",
        """<h1>Not found</h1><p>That page does not exist. Try the
<a href="/">search</a> or browse <a href="/state/">states</a>.</p>""",
        SITE + "/404.html")))

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
        pr = "1.0" if u == "/" else ("0.7" if u.count("/") <= 3 else "0.5")
        sm.append(f"<url><loc>{SITE}{u}</loc><lastmod>{today}</lastmod><priority>{pr}</priority></url>")
    sm.append("</urlset>")
    files.append(write("sitemap.xml", "\n".join(sm)))

    # ---- cache headers for Pages
    files.append(write("_headers", """/data/*
  Cache-Control: public, max-age=86400
/assets/*
  Cache-Control: public, max-age=604800
/*.html
  Cache-Control: public, max-age=3600
"""))

    print(f"records       {len(recs):,}")
    print(f"pincodes      {len(by_pincode):,} (pages generated: {len(chosen):,})")
    print(f"districts     {len(by_district):,}")
    print(f"states        {len(by_state)}")
    print(f"files written {len(files):,}")
    print(f"site size     {sum(f.stat().st_size for f in files)/1e6:.1f} MB")
    biggest = max(files, key=lambda f: f.stat().st_size)
    print(f"largest file  {biggest.relative_to(OUT).as_posix()} "
          f"{biggest.stat().st_size/1e6:.2f} MB (limit 25 MiB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pincode-limit", type=int, default=8000,
                    help="how many pincode pages to emit (Pages Free allows 20k files total)")
    build(ap.parse_args())
