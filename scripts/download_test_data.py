#!/usr/bin/env python3
"""
TraceCart -- Test Data Preparer & Downloader  v4
=================================================
Usage:
  python scripts/download_test_data.py           # offline synthetic only
  python scripts/download_test_data.py --web     # + download public clips
  python scripts/download_test_data.py --run     # + run TraceCart engine
"""
from __future__ import annotations
import argparse, json, math, os, random, subprocess, sys
import urllib.request, urllib.error
from pathlib import Path

REPO      = Path(__file__).resolve().parent.parent
CLIPS_DIR = REPO / "data" / "clips"
CACHE_DIR = REPO / "data" / "cache" / "obs"
FEEDS_DIR = REPO / "data" / "feeds"
for d in (CLIPS_DIR, CACHE_DIR, FEEDS_DIR):
    d.mkdir(parents=True, exist_ok=True)

SEP = "=" * 55
HR  = "-" * 55

# ---- 1. SYNTHETIC CLIP -------------------------------------------------------
def make_synthetic_clip(sid="REAL01", W=720, H=480, fps=30, dur=8.0):
    try:
        import cv2, numpy as np
    except ImportError:
        print("ERROR: pip install opencv-python-headless"); sys.exit(1)
    out = CLIPS_DIR / f"{sid}.mp4"
    if out.exists():
        print(f"  [skip] {out.name} already exists ({out.stat().st_size//1024} KB)")
        return out
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(out), fourcc, fps, (W, H))
    n  = int(fps * dur)
    px1,px2 = 0,int(W*0.33); bx1,bx2 = int(W*0.67),W; zy1,zy2 = int(H*0.3),int(H*0.8)
    print(f"  Rendering {n} frames -> {out.name} ...")
    for i in range(n):
        t=i/fps; p=max(0.,min(1.,(t-2.)/4.)); e=.5-.5*math.cos(math.pi*p)
        icx=int(px2*.5+(bx1+(bx2-bx1)*.5-px2*.5)*e); icy=int((zy1+zy2)/2)
        fr=np.full((H,W,3),(30,30,30),dtype="uint8")
        cv2.rectangle(fr,(px1,zy1),(px2,zy2),(60,40,40),-1)
        cv2.rectangle(fr,(bx1,zy1),(bx2,zy2),(40,60,40),-1)
        cv2.putText(fr,"Z_PICK",(px1+5,zy1+20),cv2.FONT_HERSHEY_SIMPLEX,.5,(180,80,80),1)
        cv2.putText(fr,"Z_BAG", (bx1+5,zy1+20),cv2.FONT_HERSHEY_SIMPLEX,.5,(80,180,80),1)
        cv2.rectangle(fr,(icx-20,icy-15),(icx+20,icy+15),(0,120,255),-1)
        cv2.putText(fr,"bottle",(icx-22,icy+28),cv2.FONT_HERSHEY_SIMPLEX,.38,(200,200,200),1)
        pcx=max(px1+50,icx-30)
        cv2.rectangle(fr,(pcx-30,zy1-20),(pcx+30,zy2+20),(200,180,140),2)
        cv2.putText(fr,"person",(pcx-30,zy1-25),cv2.FONT_HERSHEY_SIMPLEX,.38,(200,180,140),1)
        cv2.putText(fr,f"t={t:.2f}s f={i}",(W-170,18),cv2.FONT_HERSHEY_SIMPLEX,.42,(140,140,140),1)
        vw.write(fr)
        if i % 30 == 0: print(f"    frame {i}/{n}  t={t:.1f}s", flush=True)
    vw.release()
    print(f"  [OK] Clip saved: {out.name}  ({out.stat().st_size//1024} KB)")
    return out

# ---- 2. DETECTION CACHE ------------------------------------------------------
def make_cache(sid="REAL01", fps=30, dur=8.0, W=720, H=480, t0=1000.0):
    out = CACHE_DIR / f"obs_{sid}.jsonl"
    if out.exists():
        print(f"  [skip] {out.name} ({out.stat().st_size//1024} KB)")
        return out
    px1,px2=0,int(W*0.33); bx1,bx2=int(W*0.67),W; zy1,zy2=int(H*0.3),int(H*0.8)
    rows=[]
    for i in range(int(fps*dur)):
        t=i/fps; p=max(0.,min(1.,(t-2.)/4.)); e=.5-.5*math.cos(math.pi*p)
        icx=int(px2*.5+(bx1+(bx2-bx1)*.5-px2*.5)*e); icy=int((zy1+zy2)/2)
        rows.append({"frame":i,"t":round(t,4),"x1":icx-20,"y1":icy-15,
                     "x2":icx+20,"y2":icy+15,"class_name":"bottle",
                     "conf":round(.82+random.uniform(-.05,.05),3),"track_id":1})
        pcx=max(px1+50,icx-30)
        rows.append({"frame":i,"t":round(t,4),"x1":pcx-30,"y1":zy1-20,
                     "x2":pcx+30,"y2":zy2+20,"class_name":"person",
                     "conf":round(.91+random.uniform(-.04,.04),3),"track_id":2})
    out.write_text("\n".join(json.dumps(r) for r in rows)+"\n",encoding="utf-8")
    print(f"  [OK] Cache: {out.name}  ({len(rows)} rows)")
    return out

# ---- 3. SCAN FEED ------------------------------------------------------------
def make_feed(sid="REAL01", t0=1000.0, offset=6.5):
    fp=FEEDS_DIR/f"feed_{sid}.jsonl"; hp=FEEDS_DIR/f"hb_{sid}.jsonl"
    if fp.exists() and hp.exists():
        print(f"  [skip] feed_{sid}.jsonl + hb_{sid}.jsonl")
        return fp,hp
    ts=t0+offset
    fp.write_text(json.dumps({"event_type":"transaction_scan","s_id":f"{sid}-S001",
        "session_id":sid,"t_scan":round(ts,4),"t_ingest":round(ts+.08,4),
        "sku":"BOTL-500ML","qty":1,"price":2.49,"barcode":"5000112637922",
        "provenance":"mobile_scan"})+"\n",encoding="utf-8")
    hb=[json.dumps({"event_type":"feed_heartbeat","session_id":sid,
        "t_hb":round(t0-2+k,4),"t_ingest":round(t0-2+k+.01,4),"seq":k}) for k in range(10)]
    hp.write_text("\n".join(hb)+"\n",encoding="utf-8")
    print(f"  [OK] feed_{sid}.jsonl + hb_{sid}.jsonl")
    return fp,hp

# ---- 4. WEB DOWNLOAD ---------------------------------------------------------
# Internet Archive: genuinely open, no login, direct MP4 links
WEB_SOURCES = [
    {
        "id"  : "REAL03",
        "url" : "https://ia801906.us.archive.org/31/items/SampleVideo1280x7205mb/SampleVideo_1280x720_5mb.mp4",
        "desc": "Internet Archive sample 720p (public domain)",
        "cap_mb": 10,
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

def try_download(src):
    sid=src["id"]; url=src["url"]; desc=src["desc"]; cap=src["cap_mb"]*1024*1024
    out=CLIPS_DIR/f"{sid}.mp4"
    if out.exists():
        print(f"  [skip] {out.name} already on disk ({out.stat().st_size//1024} KB)")
        return out
    print(f"\n  Downloading: {desc}")
    print(f"  URL: {url}")
    try:
        req=urllib.request.Request(url,headers=HEADERS)
        with urllib.request.urlopen(req,timeout=60) as r:
            cl=r.getheader("Content-Length"); sz=int(cl) if cl else 0
            if sz: print(f"  File size: {sz/1024/1024:.1f} MB  (cap={src['cap_mb']} MB)")
            if sz and sz>cap: print(f"  [SKIP] Too large"); return None
            buf=b""; downloaded=0
            while True:
                chunk=r.read(512*1024)
                if not chunk: break
                buf+=chunk; downloaded+=len(chunk)
                pct=f"{downloaded/sz*100:.0f}%" if sz else "?"
                print(f"    {downloaded/1024/1024:.1f} MB  ({pct})",flush=True)
        out.write_bytes(buf)
        print(f"  [OK] Saved: {out.name}  ({len(buf)//1024} KB)")
        return out
    except (urllib.error.URLError, Exception) as ex:
        print(f"  [WARN] Failed: {ex}")
        return None

# ---- 5. ENGINE RUN -----------------------------------------------------------
# run.py derives paths from --scenario name automatically:
#   cache  = data/cache/obs/obs_{scenario}.jsonl
#   feed   = data/feeds/feed_{scenario}.jsonl
# So we just pass --scenario.
def run_engine(sid, out_dir=None):
    cache=CACHE_DIR/f"obs_{sid}.jsonl"; feed=FEEDS_DIR/f"feed_{sid}.jsonl"
    if not cache.exists():
        print(f"  [skip] obs_{sid}.jsonl not found"); return
    if not feed.exists():
        print(f"  [skip] feed_{sid}.jsonl not found"); return
    out = out_dir or (REPO/"runs"/f"demo_{sid.lower()}")
    cmd=[sys.executable,"-m","tracecart.run",
         "--scenario", sid,
         "--mode",     "cache",
         "--out",      str(out),
         "--print"]
    # PYTHONPATH=src as fallback if editable install is missing
    env=os.environ.copy()
    env["PYTHONPATH"]=str(REPO/"src")+os.pathsep+env.get("PYTHONPATH","")
    print(f"\n{HR}")
    print(f"  Running TraceCart on scenario: {sid}")
    print(f"  $ python -m tracecart.run --scenario {sid} --mode cache --print")
    print(HR, flush=True)
    result=subprocess.run(cmd, cwd=str(REPO), env=env)
    tag="[PASS]" if result.returncode==0 else f"[WARN exit={result.returncode}]"
    print(f"\n  {tag} Scenario {sid} complete")

# ---- MAIN -------------------------------------------------------------------
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--web",      action="store_true", help="Download public datasets")
    ap.add_argument("--run",      action="store_true", help="Run TraceCart after prep")
    ap.add_argument("--scenario", default="REAL01",    help="Synthetic scenario ID")
    args=ap.parse_args(); random.seed(42); T0=1000.0

    print(f"\n{SEP}")
    print("  TraceCart -- Test Data Preparation v4")
    print(SEP)

    # Step 1: synthetic
    print(f"\n[1/3] Synthetic scenario '{args.scenario}' ...")
    make_synthetic_clip(args.scenario)
    make_cache(args.scenario, t0=T0)
    make_feed(args.scenario, t0=T0)

    # Step 2: web
    web_done=[]
    if args.web:
        print(f"\n[2/3] Downloading public datasets ...")
        for src in WEB_SOURCES:
            raw=try_download(src)
            if raw and raw.exists():
                make_cache(src["id"], t0=T0+120)
                make_feed(src["id"],  t0=T0+120)
                web_done.append(src["id"])
    else:
        print(f"\n[2/3] Skipping web (pass --web to enable)")

    # Step 3: inventory
    print(f"\n[3/3] Inventory:")
    all_sids=[args.scenario]+web_done
    for sid in all_sids:
        c=CACHE_DIR/f"obs_{sid}.jsonl"; f=FEEDS_DIR/f"feed_{sid}.jsonl"
        h=FEEDS_DIR/f"hb_{sid}.jsonl"; cl=CLIPS_DIR/f"{sid}.mp4"
        ok=c.exists() and f.exists() and h.exists()
        ck=f"{cl.stat().st_size//1024}KB" if cl.exists() else "MISSING"
        tag="[OK  ]" if ok else "[WARN]"
        print(f"  {tag} {sid}  clip={ck}  cache={'YES' if c.exists() else 'NO'}  feed={'YES' if f.exists() else 'NO'}")

    print(f"\n  To test: python -m tracecart.run --scenario {args.scenario} --mode cache --print")
    print(f"{SEP}\n")

    if args.run:
        for sid in all_sids:
            run_engine(sid)

if __name__=="__main__":
    main()
