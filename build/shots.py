"""网站检查：每一页在电脑宽度和手机宽度、浅色和深色下打开，记下脚本错误、横向溢出、没画出来的图，并截整页图。
用法：python3 shots.py <调试端口> <网址（到 index.html）> <输出目录>
需要先启动：google-chrome --headless=new --remote-debugging-port=<端口> --user-data-dir=<单独目录> about:blank"""
import base64, json, os, sys, time, urllib.request
import websocket

port, base, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
page = next(t for t in tabs if t["type"] == "page")
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120, suppress_origin=True)
mid, events = 0, []

def call(method, **params):
    global mid
    mid += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == mid:
            if "error" in m: raise RuntimeError(f"{method}: {m['error']}")
            return m.get("result", {})
        events.append(m)

def js(expr):
    r = call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: raise RuntimeError(r["exceptionDetails"])
    return r["result"].get("value")

for m in ("Runtime.enable", "Page.enable", "Log.enable"): call(m)
PAGES = ["home", "rise", "early", "sector", "stocks", "drivers", "hk0307", "now", "coverage", "method"]
CHECK = """(() => {
  const pg = document.querySelector('section.page:not([hidden])');
  const charts = [...pg.querySelectorAll('.chart[data-c]')].map(c => ({id: c.dataset.c, ok: !!c.querySelector('svg, .hrows, table, .panels') && !c.querySelector('.err'), err: (c.querySelector('.err') || {}).textContent || ''}));
  const over = document.documentElement.scrollWidth - window.innerWidth;
  const wide = [...pg.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return r.right > window.innerWidth + 1 && !e.closest('.tablewrap, .plot.scroll'); }).slice(0, 5).map(e => e.tagName + '.' + e.className);
  return {title: document.title, h1: (pg.querySelector('h1') || {}).textContent, charts, over, wide, height: document.documentElement.scrollHeight};
})()"""
report = []
for width, mobile in [(1280, False), (390, True)]:
    call("Emulation.setDeviceMetricsOverride", width=width, height=900, deviceScaleFactor=1, mobile=mobile)
    for scheme in ["light", "dark"]:
        call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": scheme}])
        call("Page.navigate", url="about:blank"); time.sleep(0.2)
        events.clear()
        call("Page.navigate", url=base + "#home"); time.sleep(1.2)
        for p in PAGES:
            js(f"location.hash = '#{p}'"); time.sleep(0.6)
            info = js(CHECK)
            errs = [e for e in events if e.get("method") in ("Runtime.exceptionThrown",) or (e.get("method") == "Runtime.consoleAPICalled" and e["params"]["type"] == "error")
                    or (e.get("method") == "Log.entryAdded" and e["params"]["entry"]["level"] == "error")]
            events.clear()
            bad = [c for c in info["charts"] if not c["ok"]]
            report.append(f"{width}\t{scheme}\t{p}\t{info['title']}\tcharts {len(info['charts'])} bad {len(bad)} {bad}\tover {info['over']}\twide {info['wide']}\terrors {len(errs)} {[json.dumps(e)[:300] for e in errs]}")
            if scheme == "light" or p in ("home", "sector", "stocks"):
                h = min(info["height"], 16000)
                call("Emulation.setDeviceMetricsOverride", width=width, height=h, deviceScaleFactor=1, mobile=mobile); time.sleep(0.5)
                d = call("Page.captureScreenshot", format="png")["data"]
                open(f"{out}/{width}_{scheme}_{p}.png", "wb").write(base64.b64decode(d))
                call("Emulation.setDeviceMetricsOverride", width=width, height=900, deviceScaleFactor=1, mobile=mobile); time.sleep(0.3)
open(f"{out}/report.tsv", "w").write("\n".join(report) + "\n")
print("\n".join(report))
