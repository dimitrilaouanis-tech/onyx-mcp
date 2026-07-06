# CDN FRESHNESS SENTINEL — the silent-outage killer.
# The rhinogent CDN is the ONLY synapse between the local economy and the live
# 0n1x oracle. When the heartbeat dies quietly (July-05 class: a side-job
# exception killed the push for hours), nothing notices — the oracle just serves
# stale truth. This sentinel checks the CDN's pulse and SELF-HEALS: stale feed →
# run the heartbeat once, re-check, log everything. Scheduled q15min (OnyxCdnFresh).
import json
import os
import subprocess
import sys
import time
import urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
LOG = os.path.join(HOME, ".onyx_cdn_freshness.log")
FEED = "https://rhinogent.com/token_feed.json"
STALE_MIN = 30


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def cdn_age_min():
    import calendar
    d = json.loads(urllib.request.urlopen(FEED, timeout=20).read())
    gen = time.strptime(d["generated"], "%Y-%m-%dT%H:%M:%SZ")
    return (time.time() - calendar.timegm(gen)) / 60   # timegm = true UTC (mktime+timezone is DST-wrong)


def main():
    try:
        age = cdn_age_min()
    except Exception as e:
        log(f"SENTINEL: CDN unreadable ({e.__class__.__name__}) — healing")
        age = None
    if age is not None and age < STALE_MIN:
        if "--status" in sys.argv:
            print(f"CDN pulse: {age:.0f} min old (healthy)")
        return
    if age is not None:
        log(f"SENTINEL: CDN feed {age:.0f} min stale (limit {STALE_MIN}) — running heartbeat")
    r = subprocess.run([sys.executable, "onyx_token_heartbeat.py"],
                       capture_output=True, text=True, timeout=900)
    tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
    log("SENTINEL heal output: " + " | ".join(tail))
    try:
        age2 = cdn_age_min()
        log(f"SENTINEL: post-heal CDN age {age2:.0f} min — {'HEALED' if age2 < STALE_MIN else 'STILL STALE (investigate)'}")
    except Exception as e:
        log(f"SENTINEL: post-heal CDN still unreadable ({e.__class__.__name__})")


if __name__ == "__main__":
    main()
