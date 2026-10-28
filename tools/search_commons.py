import json, sys, urllib.parse, urllib.request

QUERIES = sys.argv[1:] or ["desk laptop cup", "office desk objects", "keys on table"]

def api(params):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "FindyMVP/0.1 (research prototype)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

for q in QUERIES:
    print("=== QUERY:", q, flush=True)
    try:
        data = api({
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": "6", "gsrlimit": "8",
            "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": "1024",
        })
        pages = (data.get("query") or {}).get("pages") or {}
        for p in pages.values():
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName") or {}).get("value", "?")
            author = (meta.get("Artist") or {}).get("value", "?")
            print(f"- {p.get('title')} | {ii.get('width')}x{ii.get('height')} | {lic}", flush=True)
            print(f"  thumb: {ii.get('thumburl')}", flush=True)
            print(f"  page: https://commons.wikimedia.org/wiki/{urllib.parse.quote(p.get('title','').replace(' ', '_'))}", flush=True)
    except Exception as e:
        print("ERR", type(e).__name__, e, flush=True)