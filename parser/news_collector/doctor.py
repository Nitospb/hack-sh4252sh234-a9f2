"""A real Chrome round trip: verify headers and JS without third-party echo sites."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from .browser import Browser


def diagnose(runtime: Path,headless=False,binary=None,driver_path=None):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"path":self.path,"headers":{k.lower():v for k,v in self.headers.items()}})
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Accept-CH","Sec-CH-UA-Platform-Version, Sec-CH-UA-Full-Version-List, Sec-CH-UA-Arch, Sec-CH-UA-Bitness")
            self.end_headers()
            self.wfile.write(("<!doctype html><html><head><title>Alfa collector local browser check</title></head><body><h1>Local Chrome diagnostic</h1><p>"+
                              "User-agent, Client Hints and JavaScript are verified locally. "*8+
                              '</p><a href="/second">Read next article</a></body></html>').encode())
        def log_message(self,*_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with Browser(runtime/"profiles"/"doctor",headless,binary,driver_path) as browser:
            url = f"http://127.0.0.1:{server.server_port}/"
            browser.read(url)
            # Second navigation verifies high-entropy hints after Accept-CH.
            browser.read(url+"second",article=True)
            js = browser.driver.execute_async_script("""
              const done=arguments[arguments.length-1];
              (async()=>done({userAgent:navigator.userAgent,platform:navigator.platform,webdriver:navigator.webdriver,
                languages:navigator.languages,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
                hints:navigator.userAgentData ? await navigator.userAgentData.getHighEntropyValues(
                  ['platformVersion','architecture','bitness','fullVersionList']) : null}))();
            """)
            headers = next(r["headers"] for r in reversed(requests) if r["path"] == "/second")
            ua = browser.identity["userAgent"]
            checks = {
                "http_ua_matches_js":headers.get("user-agent") == js["userAgent"] == ua,
                "all_requests_use_windows_ua":all(r["headers"].get("user-agent") == ua for r in requests),
                "native_link_navigation":headers.get("referer") == url,
                "windows_ua": "Windows NT 10.0; Win64; x64" in ua and not any(x in ua for x in ("Linux","Lynx","Headless")),
                "windows_js_platform":js["platform"] == "Win32",
                "webdriver_marker_disabled":js["webdriver"] is False,
                "windows_http_hints":headers.get("sec-ch-ua-platform") == '"Windows"',
                "windows_js_hints":bool(js["hints"]) and js["hints"]["platform"] == "Windows",
                "architecture_consistent":headers.get("sec-ch-ua-arch") == '"x86"' and js["hints"]["architecture"] == "x86",
                "version_consistent":all(x["version"] == browser.driver.capabilities["browserVersion"] for x in js["hints"]["fullVersionList"] if x["brand"] in ("Chromium","Google Chrome")),
            }
            report = {"ok":all(checks.values()),"mode":"headless" if headless else "headed",
                      "browser_version":browser.driver.capabilities["browserVersion"],
                      "driver_version":browser.driver.capabilities["chrome"]["chromedriverVersion"],
                      "checks":checks,"http_headers":headers,"javascript":js}
            target = runtime/"doctor"
            target.mkdir(parents=True,exist_ok=True)
            browser.driver.save_screenshot(str(target/"browser.png"))
            encoded = json.dumps(report,ensure_ascii=False,indent=2)
            (target/"report.json").write_text(encoded,encoding="utf-8")
            (target/(report["mode"]+".json")).write_text(encoded,encoding="utf-8")
            return report
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
