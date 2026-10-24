"""Second-source check for the indices used on the site's index-path page.

For each index: download the same index from a second source into data/raw/indices_more/check/ (logged like
92_fetch_more_indices.py), compare closes on common dates, and run internal checks on the primary series
(gaps longer than 10 calendar days, single-day moves above 20%). Writes data/raw/indices_more/check_report.tsv.
Run: python3 -I scripts/93_check_more_indices.py
"""
import datetime, hashlib, io, os, time, traceback, urllib.request
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data/raw"); MORE = os.path.join(RAW, "indices_more"); CHK = os.path.join(MORE, "check"); os.makedirs(CHK, exist_ok=True)
LOG = os.path.join(MORE, "fetch_log.tsv")

def load(path, date_col=None, close_col=None):
    d = pd.read_csv(path)
    dc = date_col or ("date" if "date" in d.columns else d.columns[0]); cc = close_col or ("close" if "close" in d.columns else "Close")
    s = pd.Series(pd.to_numeric(d[cc], errors="coerce").values, index=pd.to_datetime(d[dc].astype(str).str[:10], errors="coerce")).dropna()
    return s[~s.index.duplicated()].sort_index()

def second(source, symbol, fn):
    t = datetime.datetime.now().isoformat(timespec="seconds"); path = os.path.join(CHK, fn)
    try:
        if source == "yahoo":
            import yfinance as yf
            d = yf.Ticker(symbol).history(period="max", auto_adjust=False).reset_index()[["Date", "Close"]]
            d.columns = ["date", "close"]; d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
        elif source == "tx_cn":
            import akshare as ak
            d = ak.stock_zh_index_daily_tx(symbol=symbol)[["date", "close"]]
            d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        elif source == "em_hk":
            import akshare as ak
            d = ak.stock_hk_index_daily_em(symbol=symbol)
            d = d.rename(columns={"latest": "close"}) if "latest" in d.columns else d
            d = d[["date", "close"]]
        elif source == "fred":
            raw = urllib.request.urlopen(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={symbol}", timeout=60).read()
            d = pd.read_csv(io.BytesIO(raw)); d.columns = ["date", "close"]
        d = d.dropna(); d = d[pd.to_numeric(d.close, errors="coerce").notna()]
        if not len(d): raise ValueError("empty answer")
        d.to_csv(path, index=False); sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
        line = [t, source, symbol, "ok", str(len(d)), str(d.date.min()), str(d.date.max()), sha, "check/" + fn]
    except Exception as e:
        open(path + ".failed", "w").write(traceback.format_exc()); path = None
        line = [t, source, symbol, f"failed: {type(e).__name__}: {str(e)[:120]}", "0", "", "", "", "check/" + fn + ".failed"]
    open(LOG, "a").write("\t".join(line) + "\n"); time.sleep(2)
    return path

PAIRS = [  # name, primary file, second source, symbol, file
    ("沪深 300", "indices_more/sina_sh000300.csv", "tx_cn", "sh000300", "tx_sh000300.csv"),
    ("深证成指", "indices_more/sina_sz399001.csv", "yahoo", "399001.SZ", "yahoo_399001.csv"),
    ("创业板指", "indices_more/sina_sz399006.csv", "tx_cn", "sz399006", "tx_sz399006.csv"),
    ("上证 50", "indices_more/sina_sh000016.csv", "tx_cn", "sh000016", "tx_sh000016.csv"),
    ("中证 500", "indices_more/sina_sh000905.csv", "tx_cn", "sh000905", "tx_sh000905.csv"),
    ("科创 50", "indices_more/sina_sh000688.csv", "tx_cn", "sh000688", "tx_sh000688.csv"),
    ("恒生科技", "indices_more/sina_HSTECH.csv", "yahoo", "^HSTECH", "yahoo_HSTECH.csv"),
    ("国企指数", "yahoo_IDX_HSCE.csv", None, None, "../sina_HSCEI.csv"),
    ("道琼斯工业", "indices_more/yahoo_DJI.csv", "fred", "DJIA", "fred_DJIA.csv"),
    ("罗素 2000", "indices_more/yahoo_RUT.csv", None, None, None),
    ("纳斯达克综合", "yahoo_IDX_IXIC.csv", "fred", "NASDAQCOM", "fred_NASDAQCOM.csv"),
]
rows = []
for name, prim, src, sym, fn in PAIRS:
    p = load(os.path.join(RAW, prim))
    gaps = p.index.to_series().diff().dt.days; jumps = p.pct_change().abs()
    rec = {"index": name, "primary": prim, "n": len(p), "first": p.index[0].date(), "last": p.index[-1].date(),
           "max_gap_days": int(gaps.max()), "max_gap_at": gaps.idxmax().date(), "max_move": round(float(jumps.max()), 4), "max_move_at": jumps.idxmax().date()}
    sp = None
    if src: sp = second(src, sym, fn)
    elif fn: sp = os.path.normpath(os.path.join(CHK, fn))
    if sp and os.path.exists(sp):
        q = load(sp); common = p.index.intersection(q.index)
        r = (p[common] / q[common] - 1).abs()
        rec.update({"second": os.path.relpath(sp, RAW), "common_days": len(common), "median_abs_diff": round(float(r.median()), 6),
                    "share_diff_gt_0.5pct": round(float((r > 0.005).mean()), 4), "max_abs_diff": round(float(r.max()), 4), "max_diff_at": r.idxmax().date()})
    else:
        rec.update({"second": "none" if not src and not fn else "fetch failed"})
    rows.append(rec); print(rec, flush=True)
pd.DataFrame(rows).to_csv(os.path.join(MORE, "check_report.tsv"), sep="\t", index=False)
