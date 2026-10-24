"""More indices for the site's index-path page (user, 2026-10-24: 纳斯达克、沪深 300、恒生科技 …).

Downloads daily closes into data/raw/indices_more/ and logs every request to fetch_log.tsv
(time, source, symbol, status, rows, first and last date, sha256, file). A failed or empty answer is
saved as <name>.failed with the error text, never under the data file's name.
Run: python3 -I scripts/92_fetch_more_indices.py
"""
import datetime, hashlib, os, sys, time, traceback
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data/raw/indices_more"); os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "fetch_log.tsv")
JOBS = [  # (source, symbol, file)
    ("yahoo", "^DJI", "yahoo_DJI.csv"), ("yahoo", "^RUT", "yahoo_RUT.csv"),
    ("sina_cn", "sh000300", "sina_sh000300.csv"), ("sina_cn", "sz399001", "sina_sz399001.csv"), ("sina_cn", "sz399006", "sina_sz399006.csv"),
    ("sina_cn", "sh000016", "sina_sh000016.csv"), ("sina_cn", "sh000905", "sina_sh000905.csv"), ("sina_cn", "sh000688", "sina_sh000688.csv"),
    ("sina_hk", "HSTECH", "sina_HSTECH.csv"), ("sina_hk", "HSCEI", "sina_HSCEI.csv"),
]

def fetch(source, symbol):
    if source == "yahoo":
        import yfinance as yf
        d = yf.Ticker(symbol).history(period="max", auto_adjust=False)
        d = d.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "close"})
        d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
        return d
    import akshare as ak
    d = ak.stock_zh_index_daily(symbol=symbol) if source == "sina_cn" else ak.stock_hk_index_daily_sina(symbol=symbol)
    d = d[["date", "close"]].copy(); d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
    return d

if not os.path.exists(LOG):
    open(LOG, "w").write("time\tsource\tsymbol\tstatus\trows\tfirst\tlast\tsha256\tfile\n")
for source, symbol, fn in JOBS:
    t = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        d = fetch(source, symbol).dropna()
        if not len(d): raise ValueError("empty answer")
        path = os.path.join(OUT, fn); d.to_csv(path, index=False)
        sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
        line = [t, source, symbol, "ok", str(len(d)), d.date.min(), d.date.max(), sha, fn]
    except Exception as e:
        open(os.path.join(OUT, fn + ".failed"), "w").write(traceback.format_exc())
        line = [t, source, symbol, f"failed: {type(e).__name__}: {str(e)[:120]}", "0", "", "", "", fn + ".failed"]
    open(LOG, "a").write("\t".join(line) + "\n"); print("\t".join(line[:7]), flush=True)
    time.sleep(2)
