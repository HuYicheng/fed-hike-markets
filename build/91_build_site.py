"""Web site for the three-market (HK / US / A-share) Fed-hike study.

Reads only:
- the result tables of the three reports and the combined report (output/tables, output/us/tables,
  output/cn/tables, output/combined/tables);
- the Fed target rate (data/processed/fed_*.csv) and three index closes for the path chart
  (data/raw/yahoo_IDX_HSI.csv, yahoo_IDX_GSPC.csv, sina_IDX_SHCOMP.csv);
- table 5.7 of output/report.md (candidate explanations and verdicts; generated from the tables by 30_report.py).

Writes output/site/index.html (standalone page with its own doctype, for local use or any web host)
and output/site/artifact.html (the same page as a fragment, for claude.ai, which adds its own document).
With SITE_PUBLIC=1 it writes output/site_public/index.html instead: the public GitHub version, without the
stock page and without any stock-level data (stock returns come from WRDS-licensed CRSP / Compustat data).
Every number on the site is computed here from those files; check_against_reports() fails the build
if a headline number differs from the PDF reports.
"""
import datetime, html, json, os, re
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
PUBLIC = os.environ.get("SITE_PUBLIC") == "1"
OUT = "output/site_public" if PUBLIC else "output/site"; os.makedirs(OUT, exist_ok=True)
TPL = "scripts/site_template.html"
BUILT = datetime.date.today().isoformat()

MK = {"hk": {"name": "港股", "idx": "恒指", "key": "HSI", "T": "output/tables"},
      "us": {"name": "美股", "idx": "标普 500", "key": "SP500", "T": "output/us/tables"},
      "cn": {"name": "A 股", "idx": "上证综指", "key": "SHCOMP", "T": "output/cn/tables"}}
MS = list(MK)
SEC = ["能源", "原材料", "工业", "非必需消费", "必需消费", "医疗保健", "通信服务", "公用事业", "金融", "房地产", "科技"]
ALL = "ALL (EW universe)"
WN = {"h6m": "前 6 个月", "hiking": "加息期", "to_cut": "到降息"}

T0 = pd.read_csv("output/tables/T0_cycles_analysed.csv", parse_dates=["first_hike", "last_hike", "first_cut_after"]).set_index("cycle_id")
ANAL = [c for c in T0.index if pd.notna(T0.first_cut_after[c])]          # the 8 segments with a window
def single(c): return bool(T0.single_move[c])
def mw(c): return "to_cut" if single(c) else "hiking"                       # main window: hiking phase, 1997 (one hike) to the next cut
MULTI = [c for c in ANAL if not single(c)]

# ------------------------------------------------------------------ formatting
MINUS = "−"
def _s(s): return s.replace("-", MINUS)
def pc(x, d=0): return "—" if x is None or pd.isna(x) else _s(f"{x*100:+.{d}f}%")
def pc_plain(x, d=0): return "—" if x is None or pd.isna(x) else f"{x*100:.{d}f}%"
def pcu(x, d=0): return "—" if x is None or pd.isna(x) else f"{abs(x)*100:,.{d}f}%"
def most(k, n): return "多数段涨" if 2 * k > n else ("一半段涨、一半段跌" if 2 * k == n else "多数段跌")
def ppt(x, d=1): return "—" if x is None or pd.isna(x) else _s(f"{x*100:+.{d}f}") + " 个百分点"
def sn(x, d=2): return "—" if x is None or pd.isna(x) else _s(f"{x:+.{d}f}")
def pv(p): return f"p={p:.2f}" if p >= 0.01 else "p<0.01"
def esc(s): return html.escape(str(s), quote=True)
def cl(x, none="无"): return "、".join(x) if len(x) else none
def r4(x): return None if x is None or pd.isna(x) else round(float(x), 4)
def isot(d): return None if pd.isna(d) else pd.Timestamp(d).strftime("%Y-%m-%d")

# ------------------------------------------------------------------ load tables
TB = {}
for m, k in MK.items():
    T = k["T"]
    t4 = pd.read_csv(f"{T}/T4_pool.csv"); t4 = t4[t4.source == "price"] if "source" in t4.columns else t4
    t7 = pd.read_csv(f"{T}/T7_pool.csv"); t7 = t7[t7.freq == "weekly"] if "freq" in t7.columns else t7
    t12 = pd.read_csv(f"{T}/T12_pool.csv"); t12["coef"] = t12["coef_per_1sd_or_dummy"] if "coef_per_1sd_or_dummy" in t12.columns else t12["coef_per_1sd"]
    TB[m] = dict(T1=pd.read_csv(f"{T}/T1_index_returns_by_cycle.csv"), T19b=pd.read_csv(f"{T}/T19b_liquid_pool_base.csv"),
                 T19c=pd.read_csv(f"{T}/T19c_liquid_pool_base_rate.csv"), T10=pd.read_csv(f"{T}/T10_pool.csv" if m == "hk" else f"{T}/T10_base_rate.csv"),
                 T4=t4, T5=pd.read_csv(f"{T}/T5_pool.csv", dtype={"code": str}), T9=pd.read_csv(f"{T}/T9_pool.csv"),
                 T19=pd.read_csv(f"{T}/T19_liquid_pool_grid.csv"), T12=t12, T7=t7)
CB = {k[:3]: pd.read_csv(f"output/combined/tables/{k}.csv") for k in ["T30_pool_by_market", "T31_rank_correlation", "T32_sector_relative",
                                                                    "T33_sector_pooled", "T34_sector_rank_agreement", "T35_regressions", "T36_cross_section"]}
T30, T31, T32, T33, T34, T35, T36 = (CB[k] for k in ["T30", "T31", "T32", "T33", "T34", "T35", "T36"])
HK = {k: pd.read_csv(f"output/tables/{f}.csv") for k, f in [("T15b", "T15b_coverage"), ("T18", "T18_survivorship_bounds"), ("T20a", "T20a_2003_2007_index_changes"),
                                                           ("T20b", "T20b_2003_2007_regressions"), ("T20c", "T20c_2003_2007_breadth"), ("T20e", "T20e_2003_2007_events"),
                                                           ("T21a", "T21a_pe_check"), ("T21b", "T21b_decomposition"), ("T13", "T13_pool"), ("T14", "T14_pool")]}
CN = {k: pd.read_csv(f"output/cn/tables/{f}.csv") for k, f in [("T22", "T22_early_source_check"), ("T23", "T23_source_comparison"), ("T24", "T24_compustat_dividend_coverage")]}

def P(m, c, w):
    r = T30[(T30.market == m) & (T30.cycle == c) & (T30.window == w)]; return r.iloc[0] if len(r) else None
def IDX(m, c, w):
    t = TB[m]["T1"]; r = t[(t.cycle == c) & (t["index"] == MK[m]["key"])]; return r[w].iloc[0] if len(r) else np.nan
def cycles_of(m): return [c for c in ANAL if P(m, c, "h6m") is not None]

D = {"built": BUILT, "markets": {m: {"name": k["name"], "idx": k["idx"]} for m, k in MK.items()}, "sectors": SEC}

# ------------------------------------------------------------------ segments and Fed target rate
D["cycles"] = [{"id": c, "F": isot(T0.first_hike[c]), "L": isot(T0.last_hike[c]), "C": isot(T0.first_cut_after[c]), "from": float(T0.start_target[c]),
                "to": float(T0.end_target[c]), "n": int(T0.n_hikes[c]), "single": single(c), "days": int(T0.hiking_days[c]),
                "toCutDays": (int((T0.first_cut_after[c] - T0.first_hike[c]).days) if pd.notna(T0.first_cut_after[c]) else None)} for c in T0.index]
moves = pd.read_csv("data/processed/fed_moves.csv", parse_dates=["date"])
tgt = pd.read_csv("data/processed/fed_target_daily.csv", parse_dates=["date"])
segs = pd.read_csv("data/processed/fed_segments.csv", parse_dates=["first_move", "last_move", "next_segment_first_move"])
t_start = pd.Timestamp("1985-01-01")
pts = [[isot(t_start), float(tgt[tgt.date <= t_start].target.iloc[-1])]] + [[isot(r.date), float(r.target_after)] for r in moves.itertuples() if r.date > t_start]
pts.append([isot(tgt.date.iloc[-1]), float(tgt.target.iloc[-1])])
D["fed"] = {"pts": pts, "end": isot(tgt.date.iloc[-1]),
            "segs": [{"id": r.segment_id, "dir": r.direction, "F": isot(r.first_move), "L": isot(r.last_move), "next": isot(r.next_segment_first_move),
                      "n": int(r.n_moves), "from": float(r.start_target), "to": float(r.end_target), "analysed": r.segment_id in ANAL}
                     for r in segs.itertuples() if r.last_move >= t_start]}

# ------------------------------------------------------------------ pool results (T30) and index returns (T1)
D["pool"] = [{"c": r.cycle, "w": r.window, "m": r.market, "idx": r4(r["index"]), "tw": r4(r.pool_tw), "med": r4(r["median"]), "up": r4(r.pct_up), "n": int(r.n_pool)} for _, r in T30.iterrows()]
D["idx"] = {m: {c: {w: r4(IDX(m, c, w)) for w in ["h6m", "hiking", "to_cut"]} for c in ANAL if pd.notna(IDX(m, c, "h6m"))} for m in MS}

# ------------------------------------------------------------------ index paths from the first hike (=100) to the next cut
PX = {"hk": pd.read_csv("data/raw/yahoo_IDX_HSI.csv", index_col=0, parse_dates=True)["Close"],
      "us": pd.read_csv("data/raw/yahoo_IDX_GSPC.csv", index_col=0, parse_dates=True)["Close"],
      "cn": pd.read_csv("data/raw/sina_IDX_SHCOMP.csv", parse_dates=["date"]).set_index("date")["close"]}
D["paths"] = {}
for m, s in PX.items():
    s = s.astype(float).dropna(); s = s[~s.index.duplicated()].sort_index(); D["paths"][m] = {}
    for c in ANAL:
        F, L, Cc = T0.first_hike[c], T0.last_hike[c], T0.first_cut_after[c]
        if s.index[0] > F - pd.Timedelta(days=10): continue
        base = s.loc[:F].iloc[-1]; seg = s.loc[F:Cc]
        wk = seg.resample("W-FRI").last().dropna()
        xs = [(0.0, 100.0)] + [((d - F).days / 30.44, v / base * 100) for d, v in wk.items() if d > F] + [((Cc - F).days / 30.44, s.loc[:Cc].iloc[-1] / base * 100)]
        endret = s.loc[:Cc].iloc[-1] / base - 1
        assert abs(endret - IDX(m, c, "to_cut")) < 0.006, (m, c, endret, IDX(m, c, "to_cut"))
        D["paths"][m][c] = {"pts": [[round(x, 2), round(y, 2)] for x, y in xs],
                            "L": (None if single(c) else [round((L - F).days / 30.44, 2), round(s.loc[:L].iloc[-1] / base * 100, 2)])}

# ------------------------------------------------------------------ first six months against all six-month windows (T10 index, T19c pool index)
D["early"] = {}
for m in MS:
    t10, t19c = TB[m]["T10"], TB[m]["T19c"]; b, q = t10.iloc[0], t19c.iloc[0]
    D["early"][m] = {"idx": {"rows": [{"c": r.cycle, "v": r4(r.h6m), "pctile": r4(r.percentile_vs_all_6m_windows)} for r in t10.itertuples()],
                             "neg": int(b.n_negative), "n": int(b.n_hike_segments), "base": r4(b.share_negative_all_windows), "p": r4(b.binomial_p_value_two_sided),
                             "medAll": r4(b.median_all_6m_windows), "medPost": r4(b.median_post_hike_6m)},
                     "pool": {"rows": [{"c": r.cycle, "v": r4(r.liquid_pool_h6m), "pctile": r4(r.percentile_vs_all_6m_windows)} for r in t19c.itertuples()],
                              "neg": int(q.n_negative), "n": int(q.n_segments), "base": r4(q.share_negative_all_windows), "p": r4(q.binomial_p), "start": q.index_start[:7]}}
idx_start = {"hk": "1987", "us": "1985", "cn": "1991"}   # first year of the index base-rate windows, as stated in the three reports

# ------------------------------------------------------------------ sectors
D["secRel"] = [{"m": r.market, "c": r.cycle, "s": r.sector, "n": int(r.n), "med": r4(r["median"]), "up": r4(r.pct_up), "rel": r4(r.rel)} for _, r in T32.iterrows()]
D["secPool"] = [{"s": r.sector, "n": int(r.n_market_segments), "k": int(r.n_beat_own_median), "share": r4(r.share), "medRel": r4(r.median_rel), "p": r4(r.binom_p),
                 "hk": [int(r.beat_hk), int(r.n_hk)], "us": [int(r.beat_us), int(r.n_us)], "cn": [int(r.beat_cn), int(r.n_cn)]} for _, r in T33.iterrows()]
D["secAgree"] = [{"c": r.cycle, "pair": r.pair, "n": int(r.n_sectors), "rho": r4(r.rho), "p": r4(r.p)} for _, r in T34.iterrows()]
D["secAbs"] = {}
for m in MS:
    t4 = TB[m]["T4"]; rows = []
    for c in cycles_of(m):
        for s in SEC + [ALL]:
            r = t4[(t4.cycle == c) & (t4.sector == s)]
            if not len(r): continue
            r = r.iloc[0]
            rows.append({"c": c, "s": ("池内全部" if s == ALL else s), "n": int(r.n_all),
                         **{w: r4(r[f"{w}_median"]) for w in ["h6m", "hiking", "to_cut"]}, **{w + "Up": r4(r[f"{w}_pct_positive"]) for w in ["h6m", "hiking", "to_cut"]}})
    D["secAbs"][m] = rows

# ------------------------------------------------------------------ stocks: the biggest gainers and losers in each window
OLD2NEW = {"Energy": "能源", "Materials": "原材料", "Industrials": "工业", "Consumer Discretionary": "非必需消费", "Consumer Staples": "必需消费", "Healthcare": "医疗保健",
           "Telecommunications": "通信服务", "Utilities": "公用事业", "Financials": "金融", "Properties & Construction": "房地产", "Information Technology": "科技",
           "Conglomerates": "未分类(无行业标签)"}
DN = pd.read_csv("data/processed/delisted_names.csv", dtype={"code": str}).dropna(subset=["name"])
dn_map = {(c, k): (str(n)[:18] + ("（已退市）" if "Fact Book" in str(sr) else "（已退市，Yahoo 名）")) for c, k, n, sr in zip(DN.cycle, DN.code, DN.name, DN.name_source) if not str(k).startswith("C")}
def sec_cn(s): s = OLD2NEW.get(s, s); return "未分类" if str(s).startswith("未分类") else s
D["stocks"] = {}
for m in MS:
    t5 = TB[m]["T5"].copy()
    if m == "hk":
        t5 = t5[t5.qa_pass]; t5["name"] = [dn_map.get((c, k), n) for c, k, n in zip(t5.cycle, t5.code, t5.name)]; t5["label"] = t5.code
    elif m == "us": t5["label"] = t5.ticker
    else: t5["label"] = t5.code.str.replace(r"^(sh|sz)\.", "", regex=True)
    D["stocks"][m] = {}
    for c in cycles_of(m):
        g = t5[t5.cycle == c]; out = {}
        for w in ([mw(c)] + (["to_cut"] if not single(c) else [])):
            gw = g[g[w].notna()]
            def rows(df): return [{"code": str(r.label), "name": str(r["name"])[:30], "sec": sec_cn(r.sector), "h6m": r4(r.h6m), "hiking": (None if single(c) else r4(r.hiking)),
                                   "to_cut": r4(r.to_cut), "listed": bool(r.currently_listed)} for _, r in df.iterrows()]
            out[w] = {"n": int(len(gw)), "up": int((gw[w] > 0).sum()), "idx": r4(IDX(m, c, w)), "top": rows(gw.sort_values(w, ascending=False).head(10)),
                      "bottom": rows(gw.sort_values(w, ascending=True).head(10))}
        D["stocks"][m][c] = out

# ------------------------------------------------------------------ drivers: regressions (T35), cross-section (T36), dividends (T9), HK verdicts (report table 5.7)
D["reg"] = [{"m": r.market, "c": r.cycle, "r2": r4(r.r2), "robust": ([] if pd.isna(r.robust) or not str(r.robust) else str(r.robust).split("、")),
             "alpha": r4(r.pool_alpha), "t": r4(r.pool_alpha_t)} for _, r in T35.iterrows()]
FN = {"dps_growth": "窗口内分红增长", "div_yield_F": "加息前股息率", "mom12_pre": "加息前一年的涨幅", "beta_pre": "加息前对大盘的敏感度（贝塔）",
      "vol_pre": "加息前的波动", "log_turnover": "成交额", "log_mktcap": "市值", "hshare": "H 股", "ah_dual": "A+H 两地上市"}
D["xsecNames"] = FN
D["xsec"] = [{"m": r.market, "c": r.cycle, "f": r.feature, "coef": r4(r.coef), "t": r4(r.t)} for _, r in T36.iterrows()]
D["div"] = {}
for m in MS:
    t9 = TB[m]["T9"]; a = t9[t9.sector == ALL]; rows = []
    for c in cycles_of(m):
        x = a[a.cycle == c]
        if not len(x): continue
        if m == "hk":
            x = x.iloc[0]
            for w, pr, tr, dc in [("hiking", "price_ret_ew", "total_ret_ew", "dividend_contrib_ew_pp"), ("to_cut", "to_cut_price_ret_ew", "to_cut_total_ret_ew", "to_cut_dividend_contrib_ew_pp")]:
                if pd.notna(x[pr]): rows.append({"c": c, "w": w, "price": r4(x[pr]), "total": r4(x[tr]), "pp": r4(x[dc])})
        else:
            for _, y in x.iterrows(): rows.append({"c": c, "w": y.window, "price": r4(y.price_ret_ew), "total": r4(y.total_ret_ew), "pp": r4(y.dividend_contrib_ew_pp)})
    D["div"][m] = rows

def parse_md_table(path, heading):
    txt = open(path, encoding="utf-8").read(); i = txt.index(heading); lines = txt[i:].splitlines()[2:]
    rows = []
    for ln in lines:
        if not ln.startswith("|"):
            if rows: break
            continue
        cells = [x.strip() for x in ln.strip("|").split("|")]
        if set(cells[0]) <= {"-"}: continue
        rows.append(cells)
    return rows[0], rows[1:]
hdr, hyp = parse_md_table("output/report.md", "**表 5.7 候选解释与判定")
assert hdr == ["段", "候选解释", "检验", "结果", "判定"], hdr
TEST_CN = {"T13": "南向资金回归", "T13（总量）": "南向资金回归（总量）"}
def verdict_kind(v):
    head = re.split("[，；]", v)[0]
    if "不支持" in head: return "no"
    if head.startswith("看不清"): return "unclear"
    if "部分" in head or "层面" in v or "但" in head or "同步相关" in head: return "part"
    if "支持" in head: return "yes"
    return "unclear"
D["hyp"] = [{"c": r[0], "claim": r[1], "test": TEST_CN.get(r[2], r[2]), "result": r[3], "verdict": r[4], "kind": verdict_kind(r[4])} for r in hyp]

# ------------------------------------------------------------------ Hong Kong 2003-2007
T20a, T20b, T20c, T20e, T21a, T21b = (HK[k] for k in ["T20a", "T20b", "T20c", "T20e", "T21a", "T21b"])
NM = {"HSI": "恒指", "HSCEI": "国企指数", "HSI_Finance": "恒生金融分类指数", "SP500": "标普 500", "Nasdaq": "纳斯达克", "N225": "日经 225", "KS11": "韩国综合",
      "TWII": "台湾加权", "STI": "新加坡海峡时报", "JKSE": "印尼综合", "BSESN": "印度孟买 Sensex", "EEM": "新兴市场 ETF（EEM）", "SHCOMP": "上证综指",
      "Copper": "铜", "Brent": "布伦特原油", "GSCI": "标普高盛商品", "Gold": "黄金", "DXY": "美元指数", "USDCNY": "美元/人民币"}
EQ = ["HSI", "HSCEI", "SP500", "N225", "KS11", "TWII", "STI", "JKSE", "BSESN", "EEM", "SHCOMP", "Nasdaq"]
t20a = T20a.set_index("series")
D["hk0307"] = {
    "idx": [{"k": k, "name": NM[k], "eq": k in EQ, **{w: r4(t20a.loc[k, w]) for w in ["W1_2003low_2007high", "S1_2003low_2005end", "S2_2006_2007high"]}}
            for k in NM if k in t20a.index and pd.notna(t20a.loc[k, "W1_2003low_2007high"])],
    "breadth": [{"w": r.window, "g": r.group, "n": int(r.n), "med": r4(r["median"]), "up": r4(r.pct_up)} for _, r in T20c.iterrows()],
    "decomp": [{"b": r.basket, "from": int(r["from"]), "to": int(r.to), "n": int(r.n), "price": r4(r.price_return_log), "E": r4(r.E_growth_log), "PE": r4(r.PE_change_log),
                "PE0": r4(r.PE0), "PE1": r4(r.PE1), "share": r4(r.share_from_earnings)} for _, r in T21b.iterrows()],
    "events": [{"d": r.event_date, "e": r.event, "i": NM.get(r["index"], r["index"]), "d0": r4(r.day0_return), "d5": r4(r["[0,+5]"]), "d20": r4(r["[0,+20]"]),
                "p5": r4(r["placebo_pct_[0,+5]"])} for _, r in T20e.iterrows()]}

# ------------------------------------------------------------------ coverage, survivorship, thresholds, A-share source checks
T15b, T18 = HK["T15b"], HK["T18"]
D["cov"] = {"hk": [{"c": r.cycle, "nF": int(r.n_codes_with_price_at_F), "cs": int(r.n_compustat), "free": int(r.n_free_only), "hkex": (None if pd.isna(r.n_hkex_prev_yearend) else int(r.n_hkex_prev_yearend)),
                    "cov": r4(r.coverage_vs_prev_yearend), "top100": r4(r.top100_turnover_share)} for _, r in T15b.iterrows()],
            "surv": [{"c": r.cycle, "w": r.window, "reg": int(r.n_registry_listed_at_F), "miss": int(r.n_missing_registry), "share": r4(r.missing_share),
                      "obs": r4(r.median_observed), "worst": r4(r.median_worst), "best": r4(r.median_best)} for _, r in T18.iterrows() if r.n_registry_listed_at_F > 0],
            "grid": {}, "cn23": [{"c": r.cycle, "n": int(r.n), "cs": r4(r.median_compustat_price), "cst": r4(r.median_compustat_total), "bao": r4(r.median_baostock),
                                  "gt5": r4(r.share_abs_diff_gt_5pp)} for _, r in CN["T23"].iterrows()],
            "cn24": [{"y": int(r.year), "n": int(r.n_securities), "share": r4(r.share_with_dividend_recorded)} for _, r in CN["T24"].iterrows()],
            "cn22": [{"c": r.cycle, "w": r.window, "n": int(r.n), "div": r4(r.median_dividend_effect), "gt5": r4(r.share_abs_diff_gt_5pp)} for _, r in CN["T22"].iterrows()]}
for m in MS:
    g = TB[m]["T19"]; g = g[(g.window == "hiking") | ((g.cycle == "1997-03") & (g.window == "to_cut"))]
    D["cov"]["grid"][m] = [{"c": r.cycle, "share": r4(r.share_min), "cont": r4(r.cont_min), "price": r4(r.price_min), "base": bool(r.is_base), "n": int(r.n_pool), "med": r4(r["median"])}
                           for _, r in g.iterrows()]

# ================================================================== numbers used in the text
def main_med(m, c): b = P(m, c, mw(c)); return None if b is None else b["median"]
COMMON = [c for c in ANAL if all(main_med(m, c) is not None for m in MS)]
SG = []
for c in COMMON:
    v = {m: main_med(m, c) for m in MS}; best = max(v, key=v.get); worst = min(v, key=v.get)
    SG.append({"c": c, "same": len({np.sign(x) for x in v.values()}) == 1, "npos": sum(x > 0 for x in v.values()), "best": best, "worst": worst, "spread": v[best] - v[worst]})
all_neg = [s["c"] for s in SG if s["npos"] == 0]; all_pos = [s["c"] for s in SG if s["npos"] == 3]
best_cnt = {m: sum(s["best"] == m for s in SG) for m in MS}
spread_mean = np.mean([s["spread"] for s in SG])
GAP = {}
for m in MS:
    rows = [P(m, c, mw(c)) for c in cycles_of(m)]
    gaps = [r.pool_tw - r["median"] for r in rows]
    GAP[m] = {"n": len(rows), "mean": float(np.mean(gaps)), "k_below": int(sum(g > 0 for g in gaps)), "up_mean": float(np.mean([r.pct_up for r in rows]))}
COR = {r.pair: r for r in T31.itertuples()}
E = D["early"]
REG_MED = {m: float(T35[T35.market == m].r2.median()) for m in MS}
xs_sum = T36.groupby("feature").agg(n=("t", "size"), pos=("t", lambda t: int((t >= 2).sum())), neg=("t", lambda t: int((t <= -2).sum())))
SP = T33.sort_values("share", ascending=False)

def check_against_reports():
    """Headline numbers must read exactly as in the combined PDF report (output/combined/report_combined.md)."""
    rep = open("output/combined/report_combined.md", encoding="utf-8").read()
    want = [f"三地之间最大差距平均 {spread_mean*100:.0f} 个百分点",
            *[f"{r.pair} {r.rho:+.2f}（{r.n} 段，p={r.p:.2f}）" for r in T31.itertuples()],
            *[f"{MK[m]['name']} {GAP[m]['mean']*100:+.1f}pp（{GAP[m]['n']} 段中 {GAP[m]['k_below']/GAP[m]['n']*100:.0f}% 的段中位数低于加权指数）" for m in MS],
            *[f"{MK[m]['name']}：指数 {E[m]['idx']['neg']}/{E[m]['idx']['n']} 段下跌，平时 {E[m]['idx']['base']*100:.0f}%，p={E[m]['idx']['p']:.2f}" for m in MS],
            *[f"{MK[m]['name']}指数回归 R² 中位数 {REG_MED[m]:.2f}" for m in MS],
            f"窗口内分红增长在 {int(xs_sum.loc['dps_growth', 'n'])} 次检验里显著为正 {int(xs_sum.loc['dps_growth', 'pos'])} 次、显著为负 {int(xs_sum.loc['dps_growth', 'neg'])} 次",
            *[f"{r.sector} {r.n_beat_own_median}/{r.n_market_segments}" for r in SP.head(3).itertuples()]]
    bad = [s for s in want if s not in rep]
    assert not bad, "numbers differ from report_combined.md: " + " | ".join(bad)
    return len(want)
n_checked = check_against_reports()

# ================================================================== page text
def fig(cid, title, how, read="", wide=False, h=None):
    return (f'<figure class="fig{" wide" if wide else ""}"><figcaption><b>{title}</b><span class="how">{how}</span></figcaption>'
            f'<div class="chart" data-c="{cid}"{f' style="--h:{h}px"' if h else ""}><p class="nojs">图需要浏览器运行脚本才能显示。</p></div>'
            + (f'<p class="read">{read}</p>' if read else "") + "</figure>")
def page(pid, short, q, body, lede=""):
    return (f'<section class="page" id="p-{pid}" data-short="{esc(short)}" data-title="{esc(short + "：" + q)}" hidden>'
            f'<h1 class="ptitle"><span class="short">{esc(short)}</span><span class="q">：{esc(q)}</span></h1>' + (f'<div class="lede">{lede}</div>' if lede else "") + body + "</section>")
def ul(items, cls="keys"): return f'<ul class="{cls}">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"
def a(pid, text): return f'<a href="#{pid}">{text}</a>'
nm = lambda m: MK[m]["name"]
PAGES = []

# ---- home
def n_up(m, w):
    cs = cycles_of(m); return sum(P(m, c, w if w != "main" else mw(c))["median"] > 0 for c in cs), len(cs)
home_findings = [
    f"<b>同一次加息，三地常常一涨一跌。</b>三地都有个股数据的 {len(SG)} 段里，看多数股票（中位数股票），" + (f"三地同涨的 {len(all_pos)} 段（{cl(all_pos)}）" if all_pos else "三地同涨的一段也没有") + f"，同跌的 {len(all_neg)} 段（{cl(all_neg)}），"
    f"其余 {len(SG)-len(all_pos)-len(all_neg)} 段方向不一。表现最好的市场：" + "、".join(f"{nm(m)} {best_cnt[m]} 段" for m in sorted(MS, key=lambda m: -best_cnt[m]) if best_cnt[m])
    + f"。同一段里最好和最差的市场平均相差 {spread_mean*100:.0f} 个百分点。" + a("rise", "看涨跌"),
    "<b>这次港股好，不代表美股、A 股也好。</b>把各段按表现排序，三地的排序对不上：" + "，".join(f"{r.pair} {sn(r.rho)}" for r in T31.itertuples())
    + f"（1 表示排序完全一致，0 表示毫无关系）。都不显著，只有 {int(T31.n.max())} 段，看不清。" + a("rise", "看涨跌"),
    "<b>指数涨，多数股票不一定涨。</b>按成交额加权的指数平均比中位数股票多涨：" + "，".join(f"{nm(m)} {GAP[m]['mean']*100:.1f} 个百分点（{GAP[m]['n']} 段里 {GAP[m]['k_below']} 段如此）"
                                                                       for m in sorted(MS, key=lambda m: -GAP[m]["mean"])) + "。" + a("rise", "看涨跌"),
    "<b>加息后头 6 个月，只有 A 股明显更容易跌。</b>" + "；".join(
        f"{MK[m]['idx']} {E[m]['idx']['n']} 段里跌了 {E[m]['idx']['neg']} 段，平时任意 6 个月有 {E[m]['idx']['base']*100:.0f}% 在跌（{pv(E[m]['idx']['p'])}）" for m in ["cn", "hk", "us"])
    + "。p 小于 0.05 才算和平时有差别，只有 A 股达到。" + a("early", "看加息初期"),
    f"<b>没有哪个行业在加息期稳定跑赢。</b>三地合起来，跑赢本市场中位数股票的次数最多的是" + "、".join(f"{r.sector}（{r.n_market_segments} 次里 {r.n_beat_own_median} 次）" for r in SP.head(2).itertuples())
    + "，但这样的比例靠运气也常出现，没有一个行业显著。" + a("sector", "看行业"),
    "<b>宏观因素解释得少；分红增长是最一致的个股特征。</b>美国利率、油价、美元、人民币等只能解释指数每周涨跌的一小部分（各段的中位数：" + "，".join(f"{nm(m)} {REG_MED[m]*100:.0f}%" for m in MS)
    + f"）。比较同一段里的个股，加息期间分红增加得多的股票涨得更多：{int(xs_sum.loc['dps_growth', 'n'])} 次检验里 {int(xs_sum.loc['dps_growth', 'pos'])} 次显著，反向的 {int(xs_sum.loc['dps_growth', 'neg'])} 次。"
    + a("drivers", "看推动力")]
pool_sizes = {m: (int(T30[T30.market == m].n_pool.min()), int(T30[T30.market == m].n_pool.max())) for m in MS}
home = (f'<header class="hero"><p class="kicker">港股 · 美股 · A 股　1987–2024 年的 8 段加息</p><h1 class="site">美联储加息与三地股市</h1>'
        f'<p class="hlede">美联储连续几次加息算一段。1987 年 6 月以来共有 {len(T0)} 段加息，{len(ANAL)} 段已经走完（到下一次降息为止），2026-09 一段刚开始。这里把走完的每一段里，港股、美股、A 股是涨是跌、哪些行业和股票跑赢、跟着什么走，放在一起比较。</p></header>'
        + fig("fed", "联邦基金目标利率和加息段", "色块是加息期（第一次到最后一次加息），标了名字的是这里分析的 8 段；浅色块是 1987 年 6 月以前的加息段，没有分析（恒指从 1986 年底才有数据）。2008 年 12 月以后利率是目标区间的上限。2026-09 这段 9 月 17 日刚开始，还没有可看的窗口。", wide=True, h=250)
        + '<h2 class="sec">六个结论</h2><ol class="findings">' + "".join(f"<li>{x}</li>" for x in home_findings) + "</ol>"
        + fig("poolMain", "每段加息里，三地的中位数股票涨了多少", "柱子是成交活跃的股票里排在中间那只的涨跌。可以切换时间窗。1987、1988 两段只有美股有个股数据。", wide=True, h=300)
        + '<h2 class="sec">读之前先知道这几个词</h2><dl class="terms">'
        + "<dt>加息段</dt><dd>美联储连续同方向的调整算一段：连着几次加息是一段，只要中间降过一次息就另起一段，暂停不算。用第一次加息的年月命名，如 1994-02。</dd>"
        + "<dt>三个时间窗</dt><dd><b>前 6 个月</b>：第一次加息后 6 个月。<b>加息期</b>：第一次到最后一次加息。<b>到降息</b>：第一次加息到下一次降息。1997-03 那段只加了一次，没有加息期，用到降息代替。</dd>"
        + "<dt>中位数股票</dt><dd>把股票按涨跌排队，排在正中间那只的涨跌。它说的是多数股票怎么样，不受少数大公司左右。</dd>"
        + f"<dt>成交活跃的股票</dt><dd>第一次加息前 90 天，日均成交额占全市场 0.02% 以上、九成以上交易日有成交的股票，包括后来退市的。每段港股 {pool_sizes['hk'][0]}–{pool_sizes['hk'][1]} 只，美股 {pool_sizes['us'][0]}–{pool_sizes['us'][1]} 只，A 股 {pool_sizes['cn'][0]}–{pool_sizes['cn'][1]} 只。本站说的“股票”都指这些。</dd>"
        + "<dt>站得住 / 看不清</dt><dd>统计上显著（p 小于 0.05，或 t 的绝对值不小于 2）叫站得住；不显著叫看不清，意思是数据不够下结论，不是“没有关系”。</dd></dl>")
PAGES.append(f'<section class="page" id="p-home" data-short="首页" data-title="美联储加息与三地股市" hidden>{home}</section>')

# ---- rise / fall
up_main = {m: n_up(m, "main") for m in MS}; up_cut = {m: n_up(m, "to_cut") for m in MS}
sg_txt = "；".join(f"{s['c']} {nm(s['best'])}最好、{nm(s['worst'])}最差，相差 {s['spread']*100:.0f} 个百分点" for s in SG)
rise_keys = [
    "加息期（1997-03 用到降息），中位数股票上涨的段数：" + "，".join(f"{nm(m)} {up_main[m][0]}/{up_main[m][1]}" for m in MS) + "。" + "，".join(f"{nm(m)}{most(*up_main[m])}" for m in MS) + "。",
    "到降息为止：" + "，".join(f"{nm(m)} {up_cut[m][0]}/{up_cut[m][1]}" for m in MS) + "。" + "，".join(f"{nm(m)}{most(*up_cut[m])}" for m in MS) + "。",
    f"三地都有个股数据的 {len(SG)} 段里，三地同涨 {len(all_pos)} 段，同跌 {len(all_neg)} 段（{cl(all_neg)}）。{sg_txt}。",
    "按成交额加权的指数几乎总是好过中位数股票：港股 " + f"{GAP['hk']['n']} 段里 {GAP['hk']['k_below']} 段，美股 {GAP['us']['n']} 段里 {GAP['us']['k_below']} 段，A 股 {GAP['cn']['n']} 段里 {GAP['cn']['k_below']} 段。"]
rise = (ul(rise_keys)
        + fig("poolMain", "三地中位数股票的涨跌", "每组三根柱子是同一段加息里三个市场的中位数股票。切换时间窗看前 6 个月、加息期或到降息。", wide=True, h=320)
        + fig("spread", "同一段里，三地差多少", "每行是一段加息（加息期；1997-03 用到降息），三个点是三个市场的中位数股票，线的长度就是最好和最差相差多少。", h=260)
        + fig("bench", "指数、加权指数和多数股票", "每段三根柱：指数（恒指、标普 500、上证综指）、成交活跃的股票按成交额加权、中位数股票。加权指数和指数大体同向，中位数股票常常落后。", wide=True, h=300)
        + fig("breadth", "上涨股票占多少", "成交活跃的股票里上涨的比例。虚线是一半。", wide=True, h=260)
        + fig("paths", "开始加息以后，指数一路怎么走", "第一次加息那天定为 100，横轴是之后过了几个月。圆点是最后一次加息，线的终点是下一次降息。点一段的名字可以突出这一段。", wide=True, h=340)
        + '<h2 class="sec">某段港股好，美股和 A 股是不是也好</h2><p>把各段按中位数股票的表现排序，看两个市场的排序是否一致（秩相关，1 = 完全一致，−1 = 完全相反）：'
        + "，".join(f"{r.pair} {sn(r.rho)}（{r.n} 段，{pv(r.p)}）" for r in T31.itertuples()) + "。都不显著。只有 5–6 个共同的段，就算真有联系也很难看出来，所以是看不清，不是没有关系。</p>")
PAGES.append(page("rise", "涨跌", "每段加息期间，三地股市是涨是跌", rise))

# ---- first six months
def early_line(m):
    e = E[m]; i, q = e["idx"], e["pool"]
    sig = min(i["p"], q["p"]) < 0.05
    return (f"<b>{nm(m)}</b>：{MK[m]['idx']}加息后 6 个月 {i['n']} 段里跌了 {i['neg']} 段；{idx_start[m]} 年以来任意 6 个月，有 {i['base']*100:.0f}% 的时候在跌（{pv(i['p'])}）。"
            f"成交活跃的股票按成交额加权：{q['n']} 段跌了 {q['neg']} 段，平时 {q['base']*100:.0f}%（{pv(q['p'])}，从 {q['start']} 算起）。" + ("<b>和平时有显著差别。</b>" if sig else "和平时看不出差别。"))
early = (ul([early_line(m) for m in ["cn", "hk", "us"]])
         + fig("early", "加息后 6 个月的涨跌", "柱子是指数加息后 6 个月的涨跌，圆点是成交活跃的股票按成交额加权。灰色横线是平时任意 6 个月涨跌的中位数。", wide=True, h=280)
         + '<h2 class="sec">这个检验在比什么</h2><p>平时随便挑一个 6 个月，指数下跌的比例是一个基准（比如恒指 39%）。如果加息对头 6 个月没有影响，加息后下跌的段数应该和这个比例差不多。'
         + "p 值是：假如加息后和平时一样，出现这么极端的结果的机会有多大，小于 0.05 才算有差别。"
         + f"A 股 {E['cn']['idx']['n']} 段全跌，按平时 {E['cn']['idx']['base']*100:.0f}% 的下跌比例，指数这样的机会 {pv(E['cn']['idx']['p'])}，按成交额加权的口径 {pv(E['cn']['pool']['p'])}，所以说有差别。"
         + f"港股 {E['hk']['idx']['n']} 段跌 {E['hk']['idx']['neg']} 段，按平时 {E['hk']['idx']['base']*100:.0f}% 的比例并不少见（{pv(E['hk']['idx']['p'])}）。</p>"
         + f"<p>只有 {min(E[m]['idx']['n'] for m in MS)}–{max(E[m]['idx']['n'] for m in MS)} 段，即使显著，也只是这几次的事实，不能当作规律去预测下一次。</p>")
PAGES.append(page("early", "加息初期", "加息后头 6 个月，股市是不是更容易跌", early))

# ---- sectors
top_sp = SP.head(3); low_sp = SP.tail(3)
cons = [r.sector for r in SP.itertuples() if r.n_hk and r.n_us and r.n_cn and r.beat_hk / r.n_hk > 0.5 and r.beat_us / r.n_us > 0.5 and r.beat_cn / r.n_cn > 0.5]
ag_pos = T34[(T34.p < 0.05) & (T34.rho > 0)]; ag_neg = T34[(T34.p < 0.05) & (T34.rho < 0)]
sector = (ul([f"把三地所有段合起来，每个行业有 {int(SP.n_market_segments.min())}–{int(SP.n_market_segments.max())} 次机会跑赢本市场的中位数股票。跑赢次数最多的："
              + "、".join(f"{r.sector} {r.n_beat_own_median}/{r.n_market_segments}" for r in top_sp.itertuples()) + "；最少的："
              + "、".join(f"{r.sector} {r.n_beat_own_median}/{r.n_market_segments}" for r in low_sp.itertuples()) + "。" + ("没有一个行业显著偏离一半，靠运气也会出现这样的比例。" if (T33.binom_p >= 0.05).all() else ""),
              f"在三个市场里都是一半以上的段跑赢的行业：{cl(cons)}。",
              f"同一段里，两个市场的行业强弱排序是否一致：{len(T34)} 组比较里显著一致的 {len(ag_pos)} 组（" + cl([f"{r.cycle} {r.pair}" for r in ag_pos.itertuples()])
              + f"），显著相反的 {len(ag_neg)} 组。港股和 A 股在 2004、2015、2022 三段明显一致；港股与美股、美股与 A 股看不出一致。"])
          + fig("secRel", "各行业比本市场的中位数股票多涨或少涨多少", "加息期（1997-03 用到降息）。每格 = 这个行业的中位数股票减去本市场所有成交活跃股票的中位数，单位是百分点。红色跑赢，绿色跑输。股票不到 5 只的格子空着。", wide=True, h=420)
          + fig("secPool", "每个行业跑赢本市场的次数", "三地所有段合起来。虚线是一半。把鼠标移到柱子上看各市场的次数。", h=360)
          + fig("secAgree", "两个市场的行业强弱排序是否一致", "每个点是一段加息里两个市场的行业排序相关性，1 = 完全一致，−1 = 完全相反。实心点是显著的。", h=220)
          + fig("secAbs", "每个市场各行业的中位数股票涨跌", "这里是涨跌本身，不减本市场。最下面两行是全部成交活跃的股票和指数。可以切换市场和时间窗；格子里的小字是股票数。", wide=True, h=440))
PAGES.append(page("sector", "行业", "加息期间哪些行业跑赢本市场", sector))

# ---- stocks
stocks = (ul(["这里只列每段成交活跃的股票，包括后来退市的。港股只列通过价格核对的股票（两个数据源对不上的已剔除）。",
              "每段每个时间窗列涨得最多和跌得最多的 10 只。名字是数据库里的名字：港股、美股多为英文，A 股是现在的名字。",
              "个股的涨跌很极端，前 10 名代表不了多数股票；多数股票看" + a("rise", "涨跌") + "，行业看" + a("sector", "行业") + "。"])
          + fig("stocks", "涨得最多和跌得最多的股票", "选市场、加息段、时间窗。把鼠标移到柱子上看行业和其他时间窗的涨跌。", wide=True, h=430))
if not PUBLIC: PAGES.append(page("stocks", "个股", "每段加息里涨得最多、跌得最多的是哪些股票", stocks))

# ---- drivers
rob_markets = {}
for r in D["reg"]:
    for f in r["robust"]: rob_markets.setdefault(f, set()).add(r["m"])
multi_rob = [f"{f}（{'、'.join(nm(m) for m in MS if m in ms)}）" for f, ms in rob_markets.items() if len(ms) > 1]
alpha_neg = int((T35.pool_alpha < 0).sum()); alpha_n = int(T35.pool_alpha.notna().sum()); alpha_sig = T35[T35.pool_alpha_t <= -2]
dg = xs_sum.loc["dps_growth"]
hyp_counts = {k: sum(1 for h in D["hyp"] if h["kind"] == k) for k in ["yes", "part", "no", "unclear"]}
drivers = (ul([
    "指数每周的涨跌，能用美国利率、油价、美元、人民币和本地短端利率（港股、A 股另加标普 500）解释的比例，各段中位数："
    + "，".join(f"{nm(m)} {REG_MED[m]*100:.0f}%" for m in MS) + "。大部分涨跌这些因素解释不了。",
    f"在不止一个市场站得住的因素：{cl(multi_rob)}。",
    f"扣掉指数和这些因素以后，成交活跃的股票等权组合{'全是' if alpha_neg == alpha_n else '多数是'}负的：{alpha_n} 个市场-段组合里 {alpha_neg} 个为负，其中站得住的 {len(alpha_sig)} 个（"
    + cl([f"{nm(r.market)} {r.cycle}" for r in alpha_sig.itertuples()]) + "），正的站得住的 0 个。多数股票为什么系统性落后，这些数据解释不了。",
    f"比较同一段里的个股：加息期间分红增加得多的股票涨得更多，{int(dg.n)} 次检验里 {int(dg.pos)} 次站得住、反向 {int(dg.neg)} 次。其他特征（股息率、动量、贝塔、波动、成交额、市值）的方向在不同市场、不同段之间来回变。",
    f"港股的 {len(D['hyp'])} 条常见说法逐条检验：支持 {hyp_counts['yes']} 条，部分支持 {hyp_counts['part']} 条，不支持 {hyp_counts['no']} 条，看不清 {hyp_counts['unclear']} 条。"])
    + fig("r2", "宏观因素能解释指数每周涨跌的多少", "加息期（1997-03 用到降息）的周度回归。柱子越高，指数越像是跟着这些因素走。把鼠标移到柱子上看哪些因素站得住。", wide=True, h=300)
    + fig("alpha", "扣掉指数和宏观因素后，多数股票跑赢还是跑输", "成交活跃的股票等权组合，扣掉本市场指数和宏观因素能解释的部分，剩下的累计涨跌，单位是百分点。实心点是站得住的。", h=300)
    + fig("xsec", "什么样的股票在加息期涨得多", "同一段里比较个股（控制行业）。红色加号：这个特征越高的股票涨得越多，而且站得住；绿色减号：越高涨得越少；灰点：看不清；空格：没有数据。", wide=True, h=360)
    + '<h2 class="sec">港股的常见说法，数据支持吗</h2><p class="note">来自港股报告的检验：每条说法用回归、事件研究或个股比较去验证。“依据”一栏是检验结果，R² 是能解释的比例，t 的绝对值不小于 2 算站得住。</p>'
    + '<div class="tablewrap"><table class="hyp"><thead><tr><th>段</th><th>说法</th><th>判定</th><th>依据</th></tr></thead><tbody>'
    + "".join(f'<tr><td>{esc(h["c"])}</td><td>{esc(h["claim"])}</td><td><span class="vd {h["kind"]}">{esc(h["verdict"])}</span></td><td class="small">{esc(h["test"])}：{esc(h["result"])}</td></tr>' for h in D["hyp"])
    + '</tbody></table></div>'
    + fig("div", "分红多带来多少回报", "成交活跃的股票等权组合：只算股价的涨跌和算上分红的涨跌之差，单位是百分点。A 股 1994、1997、1999 段的股价已经含分红，分红记录也少，看不出来。", wide=True, h=280))
PAGES.append(page("drivers", "推动力", "股市涨跌跟着哪些因素走", drivers))

# ---- Hong Kong 2003-2007
idx_w1 = {x["k"]: x["W1_2003low_2007high"] for x in D["hk0307"]["idx"]}
OTHER = ["SP500", "N225", "KS11", "TWII", "STI", "JKSE", "BSESN", "EEM", "SHCOMP"]   # the markets compared with HSI in the HK report, section 6.1
above = [NM[k] for k in OTHER if k in idx_w1 and idx_w1[k] > idx_w1["HSI"]]
def b20(win, dep, fs):
    r = T20b[(T20b.window == win) & (T20b.dependent == dep) & (T20b.factor_set == fs)]; return r.iloc[0] if len(r) else None
rb, ra = b20("W1_2003low_2007high", "HSI", "base"), b20("W1_2003low_2007high", "HSI", "base+asia")
rsh = b20("W1_2003low_2007high", "HSI", "SHCOMP_only")
def d21(b, y0, y1): r = T21b[(T21b.basket == b) & (T21b["from"] == y0) & (T21b.to == y1)]; return r.iloc[0]
h07, x07, h67 = d21("HSI members at end-2002", 2002, 2007), d21("H shares (ISIN CNE)", 2002, 2007), d21("HSI members at end-2006", 2006, 2007)
h04, h46 = d21("HSI members at end-2002", 2002, 2004), d21("HSI members at end-2004", 2004, 2006)
br = T20c[(T20c.window == "W1_2003low_2007high")].set_index("group")
ev_hi = T20e[T20e["placebo_pct_[0,+5]"] >= 0.95]; ev_lo = T20e[T20e["placebo_pct_[0,+5]"] <= 0.05]
chk = T21a.dropna(subset=["PE_bottom_up"]); dev = (chk.PE_bottom_up / chk.PE_fact_book - 1).abs()
def ev_cls(e): return ' class="hi"' if e["p5"] >= 0.95 else (' class="lo"' if e["p5"] <= 0.05 else "")
hk0307 = (ul([f"恒指从 2003 年低点到 2007 年高点涨了 {pcu(idx_w1['HSI'])}，国企指数涨了 {pcu(idx_w1['HSCEI'])}。同期比恒指涨得多的其他股市：{cl(above)}。",
              f"恒指每周的涨跌，只用美股、利率、油价、汇率能解释 {rb.r2*100:.0f}%；加上亚洲和新兴市场股市后能解释 {ra.r2*100:.0f}%，剩下解释不了的部分{'站得住' if abs(ra.t_alpha) >= 2 else '看不清'}。"
              f"上证综指单独只能解释 {rsh.r2*100:.0f}%。这几年港股主要是跟着亚洲和新兴市场一起涨。",
              f"2002 年底的恒指成分股拿到 2007 年底涨了 {pcu(np.exp(h07.price_return_log)-1)}：{h07.share_from_earnings*100:.0f}% 来自盈利增长，其余来自市盈率从 {h07.PE0:.1f} 倍升到 {h07.PE1:.1f} 倍。"
              f"H 股涨了 {pcu(np.exp(x07.price_return_log)-1)}，{x07.share_from_earnings*100:.0f}% 来自盈利增长，市盈率从 {x07.PE0:.1f} 倍升到 {x07.PE1:.1f} 倍。",
              f"节奏不同：2004→2006 年涨幅全部来自盈利（市盈率从 {h46.PE0:.1f} 倍降到 {h46.PE1:.1f} 倍）；2006→2007 年盈利只贡献 {h67.share_from_earnings*100:.0f}%，主要是估值上升（{h67.PE0:.1f}→{h67.PE1:.1f} 倍）。",
              f"成交活跃的股票里，H 股的中位数涨了 {pcu(br.loc['liquid_pool_Hshare', 'median'])}，非 H 股涨了 {pcu(br.loc['liquid_pool_nonH', 'median'])}。"])
          + fig("hkIdx", "2003 年低点到 2007 年高点，各地股市和商品涨了多少", "恒指的低点 2003-04-25、高点 2007-10-30。切换看前后两个小段。", h=430)
          + fig("hkDecomp", "涨幅里多少来自盈利增长，多少来自估值上升", "篮子按期初成分固定不动。两段相加 = 股价涨幅（对数百分点，可以直接相加）。", wide=True, h=300)
          + f'<p class="note">市盈率是自下而上算的（年末股价 ÷ 年末前 4 个月以上已公布的每股盈利），先用港交所公布的年末市盈率核对：{len(chk)} 个年末里 {int((dev <= 0.1).sum())} 个相差不到 10%。'
          + "全部上市公司合计的拆解看不清：2002 年底全市场盈利加总接近零，比例一变就被放大，所以不列。</p>"
          + '<h2 class="sec">政策事件后指数的反应</h2><div class="tablewrap"><table class="events"><thead><tr><th>日期</th><th>事件</th><th>指数</th><th>当天</th><th>6 天</th><th>21 天</th><th>6 天的百分位</th></tr></thead><tbody>'
          + "".join(f'<tr{ev_cls(e)}><td>{e["d"]}</td><td>{esc(e["e"])}</td><td>{esc(e["i"])}</td><td>{pc(e["d0"],1)}</td><td>{pc(e["d5"],1)}</td><td>{pc(e["d20"],1)}</td><td>{e["p5"]*100:.0f}%</td></tr>' for e in D["hk0307"]["events"])
          + '</tbody></table></div>'
          + f'<p class="note">百分位是把事件后 6 天的涨跌，放到前后一年所有 6 天窗口里排位；95% 以上算异常高，5% 以下算异常低。异常高的：{cl(sorted(set(f"{x} {NM.get(y, y)}" for x, y in zip(ev_hi.event_date, ev_hi["index"]))))}；'
          + f"异常低的：{cl(sorted(set(f'{x} {NM.get(y, y)}' for x, y in zip(ev_lo.event_date, ev_lo['index']))))}。2007-08-20 同一天也是美联储下调贴现率后港股第一个交易日，亚洲股市当天都大涨，分不开是哪件事。</p>"
          + '<h2 class="sec">说不清的</h2>' + ul(["亚洲和新兴市场为什么一起涨：美元走弱、商品上涨与这些市场同时发生，但在周度回归里不显著，只能说是同时发生。",
                                                 "盈利为什么增长：数据给出了盈利，没给原因。H 股的盈利增长里混着 2005–2007 年大型国企新上市，成分变化本身就会改变篮子的盈利。",
                                                 "2003 年的自下而上市盈率和港交所公布值差得较多，这一年的拆解可信度较低。"]))
PAGES.append(page("hk0307", "2003–07 港股", "那几年恒指为什么涨得这么多", hk0307))

# ---- the 2026-09 hike
c26 = T0.loc["2026-09"]; prev_cut = segs[segs.segment_id == "2024-09"].iloc[0]
f97 = {m: P(m, "1997-03", "to_cut") for m in MS}
now = (ul([f"2026-09-17 美联储加息 {c26.total_hike_pp*100:.0f} 个基点，目标利率上限从 {c26.start_target:.2f}% 到 {c26.end_target:.2f}%。此前从 {prev_cut.first_move.date()} 到 {prev_cut.last_move.date()} 降了 {int(prev_cut.n_moves)} 次。",
           "按这里的分段规则，这是新一段加息的第一次。之后再加息，它就成为多次加息的一段；先降息，它就和 1997-03 一样是单次加息的一段。现在还没有任何时间窗可看。",
           "过去只有 1997-03 一次单次加息。从那次加息到下一次降息（1998-09-29），三地中位数股票：" + "，".join(f"{nm(m)} {pc(f97[m]['median'])}" for m in MS if f97[m] is not None)
           + "。只有一次，方向还各不相同，不能用来推断这一次。",
           "加息后头 6 个月：A 股过去 6 段全跌，和平时有显著差别；港股、美股看不出差别（见" + a("early", "加息初期") + "）。显著也只来自 6–8 段。",
           "这些数据描述的是过去加息期里股市怎么走、什么因素同时在动。它们不包含判断这一次走势的信息，也没有检验任何买卖策略。"])
       + fig("now97", "唯一一次单次加息：1997-03 以后三地指数怎么走", "1997-03-25 加息那天定为 100，横轴是之后过了几个月，线走到 1998-09-29 下一次降息。", wide=True, h=300))
PAGES.append(page("now", "这次加息", "2026 年 9 月这次，过去的数据能说明什么", now))

# ---- coverage
cov_hk = D["cov"]["hk"]; s99 = T18[(T18.cycle == "1999-06") & (T18.window == "hiking")].iloc[0]; s04 = T18[(T18.cycle == "2004-06") & (T18.window == "hiking")].iloc[0]
t23 = CN["T23"]
coverage = (ul(["<b>美股</b>：CRSP 包含 1985 年以来在三大交易所上市过的所有普通股和退市当天的收益，没有缺失公司。",
                "<b>A 股</b>：Baostock 保留了退市股，没有缺失公司。1994、1997、1999 三段的涨跌含现金分红（那几年几乎没有分红记录，去不掉），比其他段偏高，偏高多少量不出来。",
                "<b>港股</b>：以 Compustat 为主，免费数据补缺。F 日有价格的公司占港交所上年末上市公司的 " + "、".join(f"{x['c'][:4]} 年 {x['cov']*100:.0f}%" for x in cov_hk if x["cov"] is not None)
                + "（超过 100% 是因为当年新上市多于退市）。",
                f"港股仍有少数退市公司对不上价格：1999 段约占 {s99.missing_share*100:.0f}%，2004 段约 {s04.missing_share*100:.0f}%。按最坏和最好的假设加回去，1999 段全部股票的中位数在 {pc(s99.median_worst)} 到 {pc(s99.median_best)} 之间，"
                f"2004 段在 {pc(s04.median_worst)} 到 {pc(s04.median_best)} 之间（观测值 {pc(s04.median_observed)}）{'，最坏情况下由正转负' if s04.median_worst < 0 < s04.median_observed else ''}。",
                "“成交活跃”的门槛换成别的数，结论会不会变：见下面的图。门槛越高，池子越像大公司。"])
            + fig("thresh", "门槛变了，中位数股票变不变", "横轴是成交额占全市场的门槛（对数刻度），竖线是这里用的 0.02%。每条线是一段加息（加息期；1997-03 用到降息）。", wide=True, h=320)
            + fig("surv", "港股：缺失的退市公司加回去会怎样", "全部股票的中位数（不只是成交活跃的）。点是观测值，线的两端是最坏和最好假设。2022 段的退市在港交所 Fact Book 2021 之后，没法列举。", h=230)
            + fig("cn23", "A 股：两个数据源的中位数股票", "同一批成交活跃的股票、同一时间窗。Baostock 的复权价含分红，Compustat 的股价不含分红、总回报含分红。", wide=True, h=280)
            + '<p class="note">A 股的涨跌用 Baostock 的后复权价（处理了送转股、配股和股权分置改革对价），再用 Compustat 的分红记录去掉现金分红。没有直接用 Compustat 的复权价：1997–2006 年它对配股和股改对价的处理与 Baostock 不一致（上图）。'
              + "Compustat 在 2003 年以前几乎没有 A 股分红记录（有记录的证券：" + "、".join(f"{y} 年 {CN['T24'].set_index('year').loc[y, 'share_with_dividend_recorded']*100:.0f}%" for y in [1994, 1997, 1999, 2004])
              + "），所以 1994、1997、1999 三段的涨跌含现金分红。</p>")
PAGES.append(page("coverage", "数据覆盖", "数据全不全，缺的会不会改变结论", coverage))

# ---- method
seg_rows = "".join(f"<tr><td>{c['id']}</td><td>{c['F']}</td><td>{('单次' if c['single'] else c['L'])}</td><td>{c['C'] or '尚未'}</td><td>{c['from']:.2f}% → {c['to']:.2f}%</td><td>{c['n']}</td></tr>" for c in D["cycles"])
method = (ul(["<b>加息段</b>：用美联储公布的联邦基金目标利率（FRED），逐日找出每次调整。连续同方向的调整算一段，出现反向调整就另起一段，单次也成段，暂停不切段。",
              "<b>三个日期</b>：F = 第一次加息，L = 最后一次加息，C = 之后第一次降息。时间窗：前 6 个月（F 起 6 个月）、加息期（F→L）、到降息（F→C）。",
              "<b>成交活跃的股票</b>：F 日前 90 天，日均成交额占全市场 ≥ 0.02%，且有成交的交易日 ≥ 90%。包括后来退市的股票，窗口里退市或停牌的按最后成交价拿到期末（美股按退市当天的收益）。",
              "<b>涨跌</b>：只算股价，拆股、送股已调整，不含分红（A 股 1994、1997、1999 段例外，见" + a("coverage", "数据覆盖") + "）。基准价是 F 日收盘。",
              "<b>行业</b>：全球行业分类标准（GICS）的 11 个行业，已退市公司也有行业。",
              "<b>三个比较对象</b>：指数（恒指、标普 500、上证综指）；成交活跃的股票按成交额加权（单只最多 5%）；中位数股票。",
              "<b>推动力的检验</b>：指数和组合的每周涨跌对美股、美国利率、油价、美元、人民币、本地短端利率做回归，日度回归作为复核，两种都站得住才算数；"
              "个股之间比较涨幅和各种特征（同时控制行业）；加息后 6 个月和历史上任意 6 个月比较。",
              "<b>站得住</b>：p < 0.05，或 t 的绝对值 ≥ 2。看不清的意思是数据不够下结论。"])
          + '<h2 class="sec">加息段</h2><div class="tablewrap"><table class="segs"><thead><tr><th>段</th><th>F 第一次加息</th><th>L 最后一次加息</th><th>C 下一次降息</th><th>目标利率</th><th>加息次数</th></tr></thead><tbody>'
          + seg_rows + "</tbody></table></div>"
          + '<h2 class="sec">三个市场的数据</h2><div class="tablewrap"><table class="src"><thead><tr><th></th><th>港股</th><th>美股</th><th>A 股</th></tr></thead><tbody>'
          + "<tr><th>个股数据</th><td>Compustat Global（WRDS），新浪、腾讯、Yahoo 补缺和核对</td><td>CRSP（WRDS），含退市收益</td><td>Baostock（含退市股），Compustat 的分红和行业</td></tr>"
          + "<tr><th>有个股数据的段</th><td>1994 年起 6 段</td><td>1987 年起 8 段</td><td>1994 年起 6 段</td></tr>"
          + "<tr><th>指数</th><td>恒指</td><td>标普 500</td><td>上证综指</td></tr>"
          + "<tr><th>回归里的本地短端利率</th><td>3 个月 HIBOR</td><td>美国 2 年期国债</td><td>3 个月 SHIBOR（2006 年起）</td></tr>"
          + "<tr><th>缺失公司</th><td>约 1–4% 退市公司对不上价格，给了上下界</td><td>无</td><td>无</td></tr></tbody></table></div>"
          + '<h2 class="sec">比较时要记住的限制</h2>'
          + ul(["加息段很少：三地共同的只有 5–6 段。跨段规律的检验力很小，不显著多半是看不清，不是没有关系。",
                "三个市场的“成交活跃”用同一个比例门槛，但市场大小不同，池子大小也不同（" + "，".join(f"{nm(m)} {pool_sizes[m][0]}–{pool_sizes[m][1]} 只" for m in MS) + "）。",
                "美股的回归里没有“外部股市”这一项，港股和 A 股有标普 500，所以三地能解释的比例只能大致比较。",
                "这些都是过去的记录，不是对下一次的预测，也没有检验任何买卖策略。"])
          + (f'<p class="note">本网站由程序从三份报告的结果表生成，生成时核对了 {n_checked} 个关键数字与综合报告一致。个股的涨跌来自 WRDS 授权的 CRSP 和 Compustat 数据，这里只公开汇总结果，不列个股。</p>' if PUBLIC else
             f'<p class="note">原始的三份报告和综合报告（PDF）在项目文件夹的 output/ 下，生成程序在 scripts/。本网站由 scripts/91_build_site.py 从结果表生成，生成时核对了 {n_checked} 个关键数字与综合报告一致。</p>'))
PAGES.append(page("method", "怎么算的", "加息段怎么分、股票怎么选、用了哪些检验", method))

# ================================================================== write
NAV = [("home", "首页"), ("rise", "涨跌"), ("early", "加息初期"), ("sector", "行业"), ("stocks", "个股"), ("drivers", "推动力"), ("hk0307", "2003–07 港股"),
       ("now", "这次加息"), ("coverage", "数据覆盖"), ("method", "怎么算的")]
if PUBLIC:
    NAV = [x for x in NAV if x[0] != "stocks"]; del D["stocks"]
shorts = [s for _, s in NAV]; assert len(set(shorts)) == len(shorts)
for pid, s in NAV: assert f'id="p-{pid}" data-short="{s}"' in "".join(PAGES), pid
nav = "".join(f'<a href="#{pid}" data-p="{pid}">{s}</a>' for pid, s in NAV)
tpl = open(TPL, encoding="utf-8").read()
data_json = json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
body = tpl.replace("{{NAV}}", nav).replace("{{PAGES}}", "\n".join(PAGES)).replace("{{BUILT}}", BUILT).replace("{{DATA}}", data_json)
assert "{{" not in body, re.findall(r"\{\{\w+\}\}", body)
head = ('<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="description" content="1987 年 6 月以来美联储 8 段已走完的加息里，港股、美股、A 股的涨跌、行业和推动因素；数字全部从结果表计算。">\n')
if not PUBLIC: open(f"{OUT}/artifact.html", "w", encoding="utf-8").write(body)
open(f"{OUT}/index.html", "w", encoding="utf-8").write(head + body.replace("<!--HEAD-END-->", "</head><body>", 1) + "\n</body></html>\n")
if not PUBLIC:   # keep a copy of the generator next to the page, so the GitHub repo holds what built it
    import shutil
    os.makedirs(f"{OUT}/build", exist_ok=True)
    for src in ["scripts/91_build_site.py", "scripts/site_template.html", "scripts/site_checks/shots.py"]: shutil.copy2(src, f"{OUT}/build/{os.path.basename(src)}")
print(f"site: {len(body)/1024:.0f} KB, data {len(data_json)/1024:.0f} KB, {len(PAGES)} pages, {n_checked} headline numbers match report_combined.md")
