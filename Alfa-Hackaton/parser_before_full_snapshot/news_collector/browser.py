from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

STARTUP_LOCK = threading.Lock()


class PageError(RuntimeError):
    pass


class AccessBlocked(PageError):
    """A challenge or access restriction: cool down, do not hammer the source."""


@dataclass
class Page:
    requested_url: str
    url: str
    title: str
    html: str
    text: str
    status: int | None


def windows_identity(full_version: str) -> dict:
    """Chrome's reduced UA uses the real major and 0.0.0 for minor versions.

    A fixed coherent desktop identity is intentional: per-request randomization
    would contradict cookies, client hints and the actual browser's capabilities.
    """
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", full_version):
        raise ValueError(f"Unexpected Chrome version: {full_version}")
    major = full_version.split(".")[0]
    brands = [{"brand":"Not_A Brand","version":"99"},
              {"brand":"Chromium","version":major}, {"brand":"Google Chrome","version":major}]
    return {
        "userAgent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
        "acceptLanguage": "ru-RU,ru,en-US,en",
        "platform": "Win32",
        "userAgentMetadata": {"brands": brands,
            "fullVersionList": [{"brand":b["brand"],"version": "99.0.0.0" if b["version"] == "99" else full_version} for b in brands],
            "fullVersion": full_version, "platform":"Windows", "platformVersion":"10.0.0",
            "architecture":"x86", "model":"", "mobile":False, "bitness":"64", "wow64":False},
    }


class Browser:
    def __init__(self, profile: Path, headless=False, binary=None, driver_path=None):
        profile.mkdir(parents=True, exist_ok=True)
        options = webdriver.ChromeOptions()
        options.page_load_strategy = "eager"
        options.add_argument(f"--user-data-dir={profile.resolve()}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-background-networking")
        options.add_argument("--lang=ru-RU")
        options.add_argument("--window-size=1440,1000")
        options.add_experimental_option("excludeSwitches",["enable-automation"])
        # Launch-time Blink setting avoids JS prototype patches to Navigator.
        options.add_argument("--disable-blink-features=AutomationControlled")
        candidates = [binary] if binary else [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome"),shutil.which("google-chrome-stable"),
            shutil.which("chromium"),shutil.which("chromium-browser")]
        executable = next((p for p in candidates if p and Path(p).is_file()),None)
        if not executable:
            raise RuntimeError("Chrome/Chromium not found. Install Chrome or set CHROME_BINARY.")
        version_output = subprocess.check_output([executable,"--version"],text=True,timeout=10)
        match = re.search(r"\d+\.\d+\.\d+\.\d+",version_output)
        if not match:
            raise RuntimeError(f"Cannot determine Chrome version: {version_output[:120]}")
        # Applies from process startup, including initial network activity, before CDP.
        options.add_argument("--user-agent="+windows_identity(match[0])["userAgent"])
        options.binary_location = executable
        if headless:
            options.add_argument("--headless=new")
        options.set_capability("goog:loggingPrefs", {"performance":"ALL"})
        service = Service(executable_path=driver_path) if driver_path else Service()
        # Selenium Manager updates a shared cache. Serialize own startup calls
        # across threads and processes, without serializing browser navigation.
        import fcntl
        cache = Path(os.environ.get("SE_CACHE_PATH",str(Path.home()/".cache"/"selenium")))
        cache.mkdir(parents=True,exist_ok=True)
        with STARTUP_LOCK,(cache/".alfa-driver-start.lock").open("a+") as startup:
            fcntl.flock(startup,fcntl.LOCK_EX)
            try:
                self.driver = webdriver.Chrome(options=options,service=service)
            finally:
                fcntl.flock(startup,fcntl.LOCK_UN)
        try:
            self.driver.set_page_load_timeout(35)
            self.driver.set_script_timeout(15)
            self.identity = windows_identity(self.driver.capabilities["browserVersion"])
            self.driver.execute_cdp_cmd("Network.enable", {})
            self.driver.execute_cdp_cmd("Network.setUserAgentOverride", self.identity)
            self.driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId":"Europe/Moscow"})
            self._image_responses = {}
            # Version is derived each launch, so updating Chrome does not leave an old UA.
            (profile / "collector-identity.json").write_text(json.dumps(self.identity,indent=2),encoding="utf-8")
        except BaseException:
            self.driver.quit()
            raise

    def close(self):
        try:
            self.driver.quit()
        except WebDriverException:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def read(self, url: str, article=False, check_access=True, scrolls=0) -> Page:
        self._image_responses = {}
        self.driver.get_log("performance")
        try:
            clicked = False
            if article and self.driver.current_url != url:
                # Follow an actual visible listing link when available. Chrome
                # supplies normal navigation/referrer headers; do not forge them.
                try:
                    anchor = self.driver.execute_script("""
                  const clean=s=>{const u=new URL(s);u.hash='';
                    for(const k of [...u.searchParams.keys()])
                      if(k.startsWith('utm_')||['gclid','fbclid','yclid'].includes(k))u.searchParams.delete(k);
                    u.searchParams.sort();return u.href};
                  const target=clean(arguments[0]);
                  return [...document.querySelectorAll('a[href]')].find(a=>{try{return (
                    a.target!=='_blank' && a.getClientRects().length &&
                    ['http:','https:'].includes(new URL(a.href).protocol) && clean(a.href)===target
                    )}catch{return false}})||null;
                    """,url)
                except WebDriverException:
                    # Some publishers replace URL/searchParams with incomplete
                    # polyfills. Direct browser navigation remains available.
                    anchor = None
                if anchor:
                    previous = self.driver.current_url
                    try:
                        anchor.click()
                        WebDriverWait(self.driver,4).until(lambda d:d.current_url != previous)
                        clicked = True
                    except WebDriverException:
                        pass
            if not clicked:
                self.driver.get(url)
        except TimeoutException:
            self.driver.execute_script("window.stop()")
        WebDriverWait(self.driver,15).until(lambda d: d.execute_script("return !!document.body"))
        if article:
            # JS pages can populate article text after DOMContentLoaded.
            try:
                WebDriverWait(self.driver,8,poll_frequency=.4).until(
                    lambda d: d.execute_script("return !!document.querySelector('h1') && document.body.innerText.length > 350"))
            except TimeoutException:
                pass
        else:
            try:
                WebDriverWait(self.driver,6,poll_frequency=.4).until(
                    lambda d: d.execute_script("return document.querySelectorAll('a[href]').length > 3 || document.body.innerText.length > 150"))
            except TimeoutException:
                pass
        for _ in range(scrolls):
            self.driver.execute_script("window.scrollBy(0, Math.max(700, window.innerHeight * .9))")
            time.sleep(1)
        status = None
        for entry in self.driver.get_log("performance"):
            message = json.loads(entry["message"])["message"]
            if message["method"] == "Network.responseReceived" and message["params"]["type"] == "Image":
                response = message["params"]["response"]
                if int(response["status"])==200:
                    self._image_responses[response["url"]] = message["params"]["requestId"]
            if message["method"] == "Network.responseReceived" and message["params"]["type"] == "Document":
                response = message["params"]["response"]
                if response["url"].split("#")[0] == self.driver.current_url.split("#")[0]:
                    status = int(response["status"])
        page = Page(url,self.driver.current_url,self.driver.title,self.driver.page_source,
                    self.driver.execute_script("return document.body.innerText"),status)
        return self.validate_page(page,check_access)

    @staticmethod
    def validate_page(page, check_access=True):
        title = page.title.casefold()
        start = page.text[:1500].casefold()
        if page.url.startswith(("chrome-error:","chrome://","about:")) or "chrome-error://" in page.html:
            raise PageError("Navigation did not load a web page (network error or download)")
        if check_access:
            challenge = any(s in title for s in ("just a moment", "один момент", "access denied", "captcha", "доступ ограничен", "проверка браузера"))
            challenge = challenge or (len(page.text) < 2500 and any(s in start for s in (
                "verify you are human", "подтвердите, что вы не робот", "checking your browser", "проверяем ваш браузер")))
            if challenge or page.status in (401,403,429):
                raise AccessBlocked(f"Access challenge or HTTP {page.status}: {page.title[:100]}")
            if page.status and page.status >= 400:
                raise PageError(f"HTTP {page.status}: {page.url}")
        return page

    def image_bytes(self, url, max_bytes):
        """Read an already loaded response, otherwise use Chrome's network stack.

        Browser cookies and the configured UA apply; no separate HTTP client or
        cross-origin canvas is used. Resource streams are closed even on errors.
        """
        if not hasattr(self,"_media_unavailable_hosts"):
            self._media_unavailable_hosts = {}
        host = urlsplit(url).hostname
        if host in self._media_unavailable_hosts:
            raise PageError(self._media_unavailable_hosts[host])
        request_id = self._image_responses.get(url)
        if request_id:
            try:
                response = self.driver.execute_cdp_cmd("Network.getResponseBody",{"requestId":request_id})
                if len(response["body"]) > max_bytes*4//3+8:
                    raise ValueError("Image exceeds 10 MiB")
                data = base64.b64decode(response["body"]) if response.get("base64Encoded") else response["body"].encode("utf-8")
                if len(data)>max_bytes:
                    raise ValueError("Image exceeds 10 MiB")
                return data
            except WebDriverException:
                pass
        time.sleep(.4)
        frame = self.driver.execute_cdp_cmd("Page.getFrameTree",{})["frameTree"]["frame"]["id"]
        resource = self.driver.execute_cdp_cmd("Network.loadNetworkResource",{
            "frameId":frame,"url":url,"options":{"disableCache":False,"includeCredentials":True}})["resource"]
        stream = resource.get("stream")
        try:
            if not resource.get("success") or resource.get("httpStatusCode",200)>=400 or not stream:
                error = f"Image HTTP {resource.get('httpStatusCode')}: {resource.get('netErrorName','resource unavailable')}"
                if any(token in resource.get("netErrorName","") for token in ("ERR_NAME_NOT_RESOLVED","ERR_CONNECTION_TIMED_OUT","ERR_CONNECTION_REFUSED")):
                    self._media_unavailable_hosts[host] = error
                raise PageError(error)
            headers = {k.lower():str(v) for k,v in resource.get("headers",{}).items()}
            if headers.get("content-length","").isdigit() and int(headers["content-length"])>max_bytes:
                raise ValueError("Image exceeds 10 MiB")
            data = bytearray()
            while True:
                chunk = self.driver.execute_cdp_cmd("IO.read",{"handle":stream,"size":65536})
                data.extend(base64.b64decode(chunk["data"]) if chunk.get("base64Encoded") else chunk["data"].encode("utf-8"))
                if len(data)>max_bytes:
                    raise ValueError("Image exceeds 10 MiB")
                if chunk["eof"]:
                    return bytes(data)
        finally:
            if stream:
                self.driver.execute_cdp_cmd("IO.close",{"handle":stream})

    def wait_for_listing(self, page, source, timeout=8):
        """Headers may render before the actual JS news feed."""
        try:
            WebDriverWait(self.driver,timeout,poll_frequency=.5).until(lambda driver:any(
                source.accepts(url) for url in driver.execute_script("return [...document.querySelectorAll('a[href]')].map(a=>a.href)")))
        except TimeoutException:
            pass
        updated = Page(page.requested_url,self.driver.current_url,self.driver.title,self.driver.page_source,
                       self.driver.execute_script("return document.body.innerText"),page.status)
        return self.validate_page(updated)

    def diagnostic(self, directory: Path, name: str):
        directory.mkdir(parents=True,exist_ok=True)
        stem = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:80] + f"-{int(time.time())}"
        html_path = directory / (stem+".html")
        try:
            html_path.write_text(self.driver.page_source,encoding="utf-8")
            self.driver.save_screenshot(str(directory/(stem+".png")))
        except WebDriverException:
            pass
        return str(html_path)
