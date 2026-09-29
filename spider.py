"""
Core web spider / site cloner for Silent Squid.

Crawls a domain (and its subdomains), downloads all resources, and rewrites
every URL to a relative path so the saved site is fully self-contained.
"""

import hashlib
import logging
import mimetypes
import os
import re
import threading
import time
import queue
from dataclasses import dataclass, field
from typing import Callable, Optional, Set
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Matches url(...) in CSS, capturing optional quote char and the URL itself
_CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'"\)\s]+)\1\s*\)""", re.IGNORECASE)


@dataclass
class SpiderConfig:
    data_dir: str = "../temp_data"
    request_delay: float = 1.0          # seconds between requests per worker
    max_threads: int = 2                # concurrent download workers
    max_depth: int = 0                  # 0 = unlimited
    timeout: int = 30                   # HTTP request timeout (seconds)
    user_agent: str = "SilentSquid/1.0 (Web Archiver)"
    max_retries: int = 2
    follow_subdomains: bool = True
    download_images: bool = True
    download_css: bool = True
    download_js: bool = True
    max_file_size_mb: int = 50


@dataclass
class SpiderStats:
    pages_found: int = 0
    pages_downloaded: int = 0
    pages_failed: int = 0
    resources_found: int = 0
    resources_downloaded: int = 0
    resources_failed: int = 0
    bytes_downloaded: int = 0
    current_url: str = ""
    queue_size: int = 0
    running: bool = False
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        return (self.end_time or time.time()) - self.start_time

    def bytes_str(self) -> str:
        b = float(self.bytes_downloaded)
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"


class Spider:
    def __init__(self, config: SpiderConfig):
        self.config = config
        self.stats = SpiderStats()

        self._lock = threading.Lock()
        self._visited: Set[str] = set()
        self._queued: Set[str] = set()
        self._url_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._threads: list = []
        self._active_workers: int = 0
        self._session: Optional[requests.Session] = None
        self._start_netloc: str = ""
        self._base_domain: str = ""
        self._data_dir: str = ""

        # Callbacks (called from worker threads; must be thread-safe)
        self.on_stats_update: Optional[Callable] = None
        self.on_log: Optional[Callable] = None
        self.on_complete: Optional[Callable] = None

    # ------------------------------------------------------------------ public

    def start(self, url: str):
        """Begin crawling from *url*. Returns immediately; crawl runs in background."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        if not parsed.path:
            url += "/"
            parsed = urlparse(url)

        netloc = parsed.netloc.lower().split(":")[0]
        self._start_netloc = netloc
        self._base_domain = netloc[4:] if netloc.startswith("www.") else netloc
        self._data_dir = os.path.join(
            os.path.expanduser(self.config.data_dir), netloc
        )
        os.makedirs(self._data_dir, exist_ok=True)

        self._session = requests.Session()
        self._session.headers["User-Agent"] = self.config.user_agent

        self._stop_event.clear()
        with self._lock:
            self._visited.clear()
            self._queued.clear()
            self._active_workers = 0
        while not self._url_queue.empty():
            try:
                self._url_queue.get_nowait()
            except queue.Empty:
                break

        self.stats = SpiderStats(running=True, start_time=time.time())
        self._enqueue(url, is_page=True, depth=0)

        self._threads = [
            threading.Thread(target=self._worker, name=f"spider-{i}", daemon=True)
            for i in range(self.config.max_threads)
        ]
        for t in self._threads:
            t.start()

        threading.Thread(target=self._monitor, name="spider-monitor", daemon=True).start()
        self._log(f"Started crawling {url} ({self.config.max_threads} threads, "
                  f"{self.config.request_delay}s delay)")
        self._update_stats()

    def stop(self):
        """Signal all workers to stop and drain the pending queue."""
        self._stop_event.set()
        drained = 0
        while True:
            try:
                self._url_queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        for _ in self._threads:
            self._url_queue.put(None)  # poison pill per worker
        with self._lock:
            self.stats.running = False
            self.stats.end_time = time.time()
        self._log(f"Stopped (drained {drained} pending items)")
        self._update_stats()

    # --------------------------------------------------------------- internals

    def _log(self, msg: str):
        logger.info(msg)
        if self.on_log:
            self.on_log(msg)

    def _update_stats(self):
        with self._lock:
            self.stats.queue_size = self._url_queue.qsize()
        if self.on_stats_update:
            self.on_stats_update(self.stats)

    def _is_same_domain(self, url: str) -> bool:
        host = urlparse(url).netloc.lower().split(":")[0]
        if not host:
            return True  # relative URL
        bd = self._base_domain
        if host in (bd, "www." + bd, self._start_netloc):
            return True
        if self.config.follow_subdomains and host.endswith("." + bd):
            return True
        return False

    def _normalize_url(self, url: str) -> str:
        url, _ = urldefrag(url)
        p = urlparse(url)
        return urlunparse(p._replace(scheme=p.scheme.lower(), netloc=p.netloc.lower()))

    def _enqueue(self, url: str, is_page: bool, depth: int):
        url = self._normalize_url(url)
        with self._lock:
            if url in self._visited or url in self._queued:
                return
            self._queued.add(url)
            if is_page:
                self.stats.pages_found += 1
            else:
                self.stats.resources_found += 1
        self._url_queue.put((url, is_page, depth))
        self._update_stats()

    def _url_to_filepath(self, url: str) -> str:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().split(":")[0]
        path = parsed.path

        # Subdomain content lives under its own sub-directory
        if netloc != self._start_netloc:
            path = "/" + netloc + (path or "/")

        path = path.lstrip("/")

        qsuffix = ""
        if parsed.query:
            qsuffix = "_" + hashlib.md5(parsed.query.encode()).hexdigest()[:8]

        if not path or path.endswith("/"):
            dirpath = os.path.join(self._data_dir, path) if path else self._data_dir
            filename = f"index{qsuffix}.html"
        else:
            basename = os.path.basename(path)
            name, ext = os.path.splitext(basename)
            if not ext:
                dirpath = os.path.join(self._data_dir, path)
                filename = f"index{qsuffix}.html"
            else:
                dirpath = os.path.join(self._data_dir, os.path.dirname(path))
                filename = name + qsuffix + ext

        filepath = os.path.normpath(os.path.join(dirpath, filename))
        # Guard against path-traversal
        safe_root = os.path.normpath(self._data_dir)
        if not (filepath.startswith(safe_root + os.sep) or filepath == safe_root):
            filepath = os.path.join(
                self._data_dir, "misc", hashlib.md5(url.encode()).hexdigest()
            )
        return filepath

    def _make_relative(self, from_file: str, to_file: str) -> str:
        rel = os.path.relpath(to_file, os.path.dirname(from_file))
        return rel.replace(os.sep, "/")

    # ------------------------------------------------------- monitor / workers

    def _monitor(self):
        """Detects when all work is finished and fires on_complete."""
        time.sleep(2.0)
        idle_ticks = 0
        while not self._stop_event.is_set():
            time.sleep(1.0)
            with self._lock:
                active = self._active_workers
                q_size = self._url_queue.qsize()
                running = self.stats.running
            if not running:
                break
            if active == 0 and q_size == 0:
                idle_ticks += 1
                if idle_ticks >= 3:
                    with self._lock:
                        self.stats.running = False
                        self.stats.end_time = time.time()
                    self._log("Crawl completed!")
                    self._update_stats()
                    if self.on_complete:
                        self.on_complete()
                    break
            else:
                idle_ticks = 0

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                item = self._url_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:
                break

            url, is_page, depth = item
            with self._lock:
                self._active_workers += 1
                self.stats.current_url = url

            self._update_stats()
            try:
                if is_page:
                    self._process_page(url, depth)
                else:
                    self._process_resource(url)
            except Exception as exc:
                self._log(f"Error processing {url}: {exc}")
                with self._lock:
                    if is_page:
                        self.stats.pages_failed += 1
                    else:
                        self.stats.resources_failed += 1
            finally:
                with self._lock:
                    self._visited.add(url)
                    self._active_workers -= 1
                self._update_stats()

            if not self._stop_event.is_set():
                time.sleep(self.config.request_delay)

    # ----------------------------------------------------------------- fetching

    def _fetch(self, url: str) -> Optional[requests.Response]:
        for attempt in range(self.config.max_retries + 1):
            try:
                resp = self._session.get(
                    url,
                    timeout=self.config.timeout,
                    allow_redirects=True,
                )
                resp.raise_for_status()
                return resp
            except requests.HTTPError as exc:
                self._log(f"HTTP {exc.response.status_code} for {url}")
                return None
            except requests.RequestException as exc:
                if attempt < self.config.max_retries:
                    self._log(f"Retry {attempt + 1}/{self.config.max_retries} for {url}: {exc}")
                    time.sleep(1.0)
                else:
                    self._log(f"Failed: {url} — {exc}")
                    return None
        return None

    def _save_file(self, filepath: str, content: bytes):
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(filepath, "wb") as fh:
            fh.write(content)

    # ------------------------------------------------------- page processing

    def _process_page(self, url: str, depth: int):
        resp = self._fetch(url)
        if resp is None:
            with self._lock:
                self.stats.pages_failed += 1
            return

        content_type = resp.headers.get("Content-Type", "").lower()
        content = resp.content
        max_bytes = self.config.max_file_size_mb * 1024 * 1024

        if len(content) > max_bytes:
            self._log(f"Skipping (too large): {url}")
            return

        if "html" not in content_type:
            # Linked as a page but it's actually a binary resource
            self._save_resource(resp, url)
            return

        filepath = self._url_to_filepath(url)

        try:
            soup = BeautifulSoup(content, "lxml")
        except Exception:
            soup = BeautifulSoup(content, "html.parser")

        # Use <base href> as effective base URL if present, then remove it
        base_tag = soup.find("base", href=True)
        base_url = urljoin(url, base_tag["href"].strip()) if base_tag else url
        if base_tag:
            base_tag.decompose()

        # ---- anchor tags (followed pages) ----
        for tag in soup.find_all("a", href=True):
            self._rewrite_tag(tag, "href", base_url, filepath, depth,
                              is_page=True, skip_ext=True)

        # ---- link tags (CSS, favicon, …) ----
        if self.config.download_css:
            for tag in soup.find_all("link", href=True):
                self._rewrite_tag(tag, "href", base_url, filepath, depth, is_page=False)

        # ---- script tags ----
        if self.config.download_js:
            for tag in soup.find_all("script", src=True):
                self._rewrite_tag(tag, "src", base_url, filepath, depth, is_page=False)

        # ---- img tags (src + srcset) ----
        if self.config.download_images:
            for tag in soup.find_all("img"):
                for attr in ("src", "data-src", "data-lazy-src"):
                    if tag.get(attr):
                        self._rewrite_tag(tag, attr, base_url, filepath, depth, is_page=False)
                if tag.get("srcset"):
                    tag["srcset"] = self._rewrite_srcset(
                        tag["srcset"], base_url, filepath, depth
                    )

        # ---- picture / video / audio sources ----
        for tag in soup.find_all("source"):
            for attr in ("src", "srcset"):
                if tag.get(attr):
                    if attr == "srcset":
                        tag[attr] = self._rewrite_srcset(
                            tag[attr], base_url, filepath, depth
                        )
                    else:
                        self._rewrite_tag(tag, attr, base_url, filepath, depth, is_page=False)

        # ---- inline style url() ----
        for tag in soup.find_all(style=True):
            tag["style"] = self._rewrite_css_text(tag["style"], base_url, filepath, depth)

        # ---- <style> blocks ----
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                style_tag.string = self._rewrite_css_text(
                    style_tag.string, base_url, filepath, depth
                )

        # ---- meta refresh ----
        for tag in soup.find_all("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)}):
            ct = tag.get("content", "")
            m = re.search(r"url=(.+)", ct, re.I)
            if m:
                redir = urljoin(base_url, m.group(1).strip().strip("\"'"))
                redir = self._normalize_url(redir)
                if self._is_same_domain(redir) and (self.config.max_depth == 0 or depth < self.config.max_depth):
                    self._enqueue(redir, is_page=True, depth=depth + 1)

        self._save_file(filepath, soup.encode())
        with self._lock:
            self.stats.pages_downloaded += 1
            self.stats.bytes_downloaded += len(content)
        self._log(f"Saved page: {filepath}")
        self._update_stats()

    # ---------------------------------------------------- resource processing

    def _process_resource(self, url: str):
        resp = self._fetch(url)
        if resp is None:
            with self._lock:
                self.stats.resources_failed += 1
            return
        self._save_resource(resp, url)

    def _save_resource(self, resp: requests.Response, url: str):
        content_type = resp.headers.get("Content-Type", "").lower()
        content = resp.content
        max_bytes = self.config.max_file_size_mb * 1024 * 1024

        if len(content) > max_bytes:
            self._log(f"Skipping large resource: {url}")
            return

        filepath = self._url_to_filepath(url)

        # Append a guessed extension when the URL has none
        _, ext = os.path.splitext(filepath)
        if not ext:
            main_ct = content_type.split(";")[0].strip()
            guessed = mimetypes.guess_extension(main_ct)
            if guessed:
                filepath += guessed

        if "css" in content_type or filepath.endswith(".css"):
            content = self._rewrite_css_bytes(content, url, filepath)

        self._save_file(filepath, content)
        with self._lock:
            self.stats.resources_downloaded += 1
            self.stats.bytes_downloaded += len(content)
        self._log(f"Saved resource: {filepath}")
        self._update_stats()

    # --------------------------------------------------- URL rewriting helpers

    def _rewrite_tag(
        self,
        tag,
        attr: str,
        base_url: str,
        page_filepath: str,
        depth: int,
        is_page: bool,
        skip_ext: bool = False,
    ):
        """Resolve, enqueue, and rewrite a single tag attribute in place."""
        val = (tag.get(attr) or "").strip()
        if not val or val.startswith(("#", "data:", "mailto:", "javascript:", "tel:")):
            return

        # Skip binary file extensions when following anchor links
        if skip_ext and is_page:
            _, ext = os.path.splitext(val.split("?")[0])
            if ext.lower() in {
                ".pdf", ".zip", ".gz", ".tar", ".exe", ".dmg", ".pkg",
                ".mp4", ".mp3", ".avi", ".mov", ".wmv", ".flv",
            }:
                return

        abs_url = self._normalize_url(urljoin(base_url, val))
        if not self._is_same_domain(abs_url):
            return

        if is_page:
            if self.config.max_depth > 0 and depth >= self.config.max_depth:
                return
            self._enqueue(abs_url, is_page=True, depth=depth + 1)
        else:
            self._enqueue(abs_url, is_page=False, depth=depth)

        target = self._url_to_filepath(abs_url)
        tag[attr] = self._make_relative(page_filepath, target)

    def _rewrite_srcset(self, srcset: str, base_url: str, page_filepath: str, depth: int) -> str:
        parts = []
        for segment in srcset.split(","):
            tokens = segment.strip().split()
            if not tokens:
                parts.append(segment)
                continue
            src = tokens[0]
            if not src.startswith("data:"):
                abs_url = self._normalize_url(urljoin(base_url, src))
                if self._is_same_domain(abs_url):
                    self._enqueue(abs_url, is_page=False, depth=depth)
                    tokens[0] = self._make_relative(page_filepath, self._url_to_filepath(abs_url))
            parts.append(" ".join(tokens))
        return ", ".join(parts)

    def _rewrite_css_text(
        self, text: str, base_url: str, from_filepath: str, depth: int
    ) -> str:
        def replace(m: re.Match) -> str:
            quote = m.group(1)
            raw = m.group(2)
            if raw.startswith(("data:", "#")):
                return m.group(0)
            abs_url = self._normalize_url(urljoin(base_url, raw))
            if not self._is_same_domain(abs_url):
                return m.group(0)
            self._enqueue(abs_url, is_page=False, depth=depth)
            rel = self._make_relative(from_filepath, self._url_to_filepath(abs_url))
            return f"url({quote}{rel}{quote})"

        return _CSS_URL_RE.sub(replace, text)

    def _rewrite_css_bytes(self, content: bytes, base_url: str, filepath: str) -> bytes:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            return content
        return self._rewrite_css_text(text, base_url, filepath, 0).encode("utf-8")
