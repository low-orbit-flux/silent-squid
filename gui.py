"""
Cross-platform desktop GUI for Silent Squid web spider.

Two tabs:
  DOWNLOAD  — enter a URL, configure settings, view live stats + log
  SITES     — browse previously cloned sites; open in system browser
"""

import os
import queue
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import theme
from spider import Spider, SpiderConfig, SpiderStats

_POLL_MS = 100  # GUI update interval (ms)


class SpiderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SILENT SQUID  //  WEB CRAWLER")
        self.root.geometry("980x740")
        self.root.minsize(740, 560)

        # Apply theme first — must happen before any widgets are created
        self._fonts = theme.setup(self.root)

        self._spider: Optional[Spider] = None
        self._update_queue: queue.Queue = queue.Queue()
        self._data_dir_var = tk.StringVar(value="../temp_data")
        self._blink_job = None
        self._blink_state = 0

        self._build_ui()
        self._schedule_poll()

    # ─────────────────────────────────────────────────────────── build UI ────

    def _build_ui(self):
        # ── top banner ────────────────────────────────────────────────────────
        banner = tk.Frame(self.root, bg=theme.BG_HEADER, pady=8)
        banner.pack(fill=tk.X, side=tk.TOP)
        tk.Label(
            banner,
            text="SILENT SQUID",
            bg=theme.BG_HEADER, fg=theme.ACCENT,
            font=self._fonts["header"],
        ).pack()
        tk.Label(
            banner,
            text=">>  web crawler  &  offline site cloner  <<",
            bg=theme.BG_HEADER, fg=theme.FG_DIM,
            font=self._fonts["sub"],
        ).pack()

        # thin separator line under banner
        tk.Frame(self.root, bg=theme.BORDER, height=1).pack(fill=tk.X)

        # ── menu ──────────────────────────────────────────────────────────────
        menubar = tk.Menu(
            self.root,
            bg=theme.BG_BTN, fg=theme.FG,
            activebackground=theme.BG_ACTIVE, activeforeground=theme.ACCENT,
            borderwidth=0, relief="flat",
        )
        self.root.config(menu=menubar)
        file_menu = tk.Menu(
            menubar, tearoff=0,
            bg=theme.BG_BTN, fg=theme.FG,
            activebackground=theme.BG_ACTIVE, activeforeground=theme.ACCENT,
        )
        file_menu.add_command(label="Set Data Directory…", command=self._browse_data_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="FILE", menu=file_menu)

        # ── notebook ──────────────────────────────────────────────────────────
        self._nb = ttk.Notebook(self.root)
        self._nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._dl_frame    = ttk.Frame(self._nb)
        self._sites_frame = ttk.Frame(self._nb)
        self._nb.add(self._dl_frame,    text="  DOWNLOAD  ")
        self._nb.add(self._sites_frame, text="  SITES  ")

        self._build_download_tab()
        self._build_sites_tab()

    # ──────────────────────────────────────────────────────── Download tab ───

    def _build_download_tab(self):
        f = self._dl_frame

        # ── parameters group ──────────────────────────────────────────────────
        cfg = ttk.LabelFrame(f, text="//  PARAMETERS  //", padding=10)
        cfg.pack(fill=tk.X, padx=10, pady=(10, 4))
        cfg.columnconfigure(1, weight=1)

        # URL row
        ttk.Label(cfg, text="TARGET :", style="Dim.TLabel", anchor=tk.E, width=12).grid(
            row=0, column=0, sticky=tk.E, pady=4)
        self._url_var = tk.StringVar()
        url_entry = ttk.Entry(cfg, textvariable=self._url_var)
        url_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0), pady=4)
        url_entry.bind("<Return>", lambda _: self._start_crawl())

        # Data dir row
        ttk.Label(cfg, text="DATA DIR :", style="Dim.TLabel", anchor=tk.E, width=12).grid(
            row=1, column=0, sticky=tk.E, pady=4)
        data_row = ttk.Frame(cfg)
        data_row.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0), pady=4)
        ttk.Entry(data_row, textvariable=self._data_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(data_row, text="BROWSE", width=8,
                   command=self._browse_data_dir).pack(side=tk.LEFT, padx=(6, 0))

        # Separator
        ttk.Separator(cfg, orient=tk.HORIZONTAL).grid(
            row=2, column=0, columnspan=3, sticky=tk.EW, pady=(8, 4))

        # Numeric settings row
        nums = ttk.Frame(cfg)
        nums.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(2, 4), padx=2)

        ttk.Label(nums, text="DELAY (s) :", style="Dim.TLabel").pack(side=tk.LEFT)
        self._delay_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(nums, textvariable=self._delay_var, from_=0.0, to=60.0,
                    increment=0.5, width=6, format="%.1f").pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(nums, text="THREADS :", style="Dim.TLabel").pack(side=tk.LEFT)
        self._threads_var = tk.IntVar(value=2)
        ttk.Spinbox(nums, textvariable=self._threads_var, from_=1, to=16,
                    width=4).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(nums, text="MAX DEPTH :", style="Dim.TLabel").pack(side=tk.LEFT)
        self._depth_var = tk.IntVar(value=0)
        ttk.Spinbox(nums, textvariable=self._depth_var, from_=0, to=999,
                    width=4).pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(nums, text="[ 0 = unlimited ]", style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(2, 16))

        self._dl_images = tk.BooleanVar(value=True)
        self._dl_css    = tk.BooleanVar(value=True)
        self._dl_js     = tk.BooleanVar(value=True)
        ttk.Checkbutton(nums, text="IMAGES", variable=self._dl_images).pack(side=tk.LEFT)
        ttk.Checkbutton(nums, text="CSS",    variable=self._dl_css).pack(
            side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(nums, text="JS",     variable=self._dl_js).pack(
            side=tk.LEFT, padx=(8, 0))

        # Action buttons
        btns = ttk.Frame(cfg)
        btns.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=(10, 2))
        self._start_btn = ttk.Button(
            btns, text="[ EXECUTE ]", command=self._start_crawl, width=14)
        self._start_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._stop_btn = ttk.Button(
            btns, text="[ ABORT ]", command=self._stop_crawl, width=10, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT)

        # ── telemetry group ───────────────────────────────────────────────────
        telem = ttk.LabelFrame(f, text="//  TELEMETRY  //", padding=10)
        telem.pack(fill=tk.X, padx=10, pady=4)
        telem.columnconfigure(1, weight=1)

        self._stat_vars: dict = {}
        rows = [
            ("status",     "SYS.STATUS :",   "-- STANDBY --"),
            ("current",    "TARGET :",        ""),
            ("pages",      "PAGES :",         "0 found   0 downloaded   0 failed"),
            ("resources",  "ASSETS :",        "0 found   0 downloaded   0 failed"),
            ("queue",      "QUEUE :",         "0 items"),
            ("downloaded", "BYTES.RECV :",    "0 B"),
            ("elapsed",    "UPTIME :",        "0s"),
        ]
        for row_i, (key, label, default) in enumerate(rows):
            ttk.Label(telem, text=label, style="Dim.TLabel",
                      anchor=tk.E, width=16).grid(
                row=row_i, column=0, sticky=tk.E, pady=2)
            var = tk.StringVar(value=default)
            self._stat_vars[key] = var
            fg = theme.ACCENT if key == "status" else theme.FG
            ttk.Label(telem, textvariable=var, anchor=tk.W,
                      foreground=fg, font=self._fonts["mono"]).grid(
                row=row_i, column=1, sticky=tk.EW, padx=(10, 0), pady=2)

        # ── system log group ──────────────────────────────────────────────────
        log_outer = ttk.LabelFrame(f, text="//  SYSTEM LOG  //", padding=6)
        log_outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        self._log_text = tk.Text(
            log_outer,
            height=8, wrap=tk.WORD, state=tk.DISABLED,
            font=self._fonts["mono"],
            bg=theme.BG_INPUT, fg=theme.FG_DIM,
            insertbackground=theme.CURSOR,
            selectbackground=theme.SEL_BG, selectforeground=theme.SEL_FG,
            relief="flat", borderwidth=0,
        )
        vscroll = ttk.Scrollbar(log_outer, orient=tk.VERTICAL,
                                 command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

    # ─────────────────────────────────────────────────────────── Sites tab ───

    def _build_sites_tab(self):
        pw = ttk.PanedWindow(self._sites_frame, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── left: index list ──────────────────────────────────────────────────
        left = ttk.Frame(pw, width=220)
        pw.add(left, weight=1)

        ttk.Label(left, text="//  SITE INDEX  //",
                  style="Dim.TLabel").pack(anchor=tk.W, pady=(0, 6))

        lf = ttk.Frame(left)
        lf.pack(fill=tk.BOTH, expand=True)
        self._sites_lb = tk.Listbox(
            lf,
            selectmode=tk.SINGLE, activestyle="none",
            bg=theme.BG_INPUT, fg=theme.FG_DIM,
            selectbackground=theme.SEL_BG, selectforeground=theme.ACCENT,
            font=self._fonts["mono"],
            relief="flat", borderwidth=0,
            highlightthickness=1, highlightcolor=theme.BORDER,
            highlightbackground=theme.BORDER,
        )
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self._sites_lb.yview)
        self._sites_lb.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._sites_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._sites_lb.bind("<<ListboxSelect>>", self._on_site_selected)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="[ SCAN ]",
                   command=self._refresh_sites).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="[ VIEW ]",
                   command=self._open_in_browser).pack(side=tk.LEFT, padx=(6, 0))

        # ── right: file tree ──────────────────────────────────────────────────
        right = ttk.Frame(pw)
        pw.add(right, weight=4)

        self._site_info_var = tk.StringVar(value="select a target from the index  >")
        ttk.Label(right, textvariable=self._site_info_var, style="Dim.TLabel",
                  anchor=tk.W, wraplength=560).pack(fill=tk.X, pady=(0, 6))

        tree_frame = ttk.Frame(right)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self._tree = ttk.Treeview(
            tree_frame, show="tree", selectmode="browse", columns=("path",))
        self._tree.column("#0", minwidth=200)
        self._tree.column("path", width=0, stretch=False)

        tree_vs = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,  command=self._tree.yview)
        tree_hs = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=tree_vs.set, xscrollcommand=tree_hs.set)
        tree_hs.pack(side=tk.BOTTOM, fill=tk.X)
        tree_vs.pack(side=tk.RIGHT,  fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.bind("<<TreeviewOpen>>", self._on_tree_expand)
        self._tree.bind("<Double-1>",        self._on_tree_dblclick)

    # ──────────────────────────────────────────────────── download actions ───

    def _browse_data_dir(self):
        d = filedialog.askdirectory(
            title="Select Data Directory",
            initialdir=os.path.expanduser(self._data_dir_var.get()),
        )
        if d:
            self._data_dir_var.set(d)

    def _start_crawl(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning("INPUT REQUIRED", "Please enter a target URL.")
            return
        if self._spider and self._spider.stats.running:
            messagebox.showinfo("ALREADY RUNNING", "A crawl is already in progress.")
            return

        cfg = SpiderConfig(
            data_dir=self._data_dir_var.get().strip() or "../temp_data",
            request_delay=self._delay_var.get(),
            max_threads=self._threads_var.get(),
            max_depth=self._depth_var.get(),
            download_images=self._dl_images.get(),
            download_css=self._dl_css.get(),
            download_js=self._dl_js.get(),
        )
        self._spider = Spider(cfg)
        self._spider.on_stats_update = lambda s: self._update_queue.put(("stats", s))
        self._spider.on_log          = lambda m: self._update_queue.put(("log",   m))
        self._spider.on_complete     = lambda:   self._update_queue.put(("complete", None))

        self._clear_log()
        self._start_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.NORMAL)
        self._blink_state = 0
        self._start_blink()
        self._spider.start(url)

    def _stop_crawl(self):
        if self._spider:
            self._spider.stop()
        self._stop_blink()
        self._start_btn.configure(state=tk.NORMAL)
        self._stop_btn.configure(state=tk.DISABLED)

    # ──────────────────────────────────────────── status blink animation ─────

    def _start_blink(self):
        self._stop_blink()
        self._do_blink()

    def _stop_blink(self):
        if self._blink_job:
            self.root.after_cancel(self._blink_job)
            self._blink_job = None

    def _do_blink(self):
        dots = "." * (self._blink_state % 4)
        self._stat_vars["status"].set(f">> CRAWLING{dots:<3}")
        self._blink_state += 1
        self._blink_job = self.root.after(400, self._do_blink)

    # ─────────────────────────────────────────────────────────── log / stats ──

    def _clear_log(self):
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _append_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"[{ts}]  {msg}\n")
        self._log_text.see(tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _apply_stats(self, stats: SpiderStats):
        current = stats.current_url
        if len(current) > 90:
            current = current[:87] + "…"
        self._stat_vars["current"].set(current)
        self._stat_vars["pages"].set(
            f"{stats.pages_found} found   "
            f"{stats.pages_downloaded} downloaded   "
            f"{stats.pages_failed} failed"
        )
        self._stat_vars["resources"].set(
            f"{stats.resources_found} found   "
            f"{stats.resources_downloaded} downloaded   "
            f"{stats.resources_failed} failed"
        )
        self._stat_vars["queue"].set(f"{stats.queue_size} items")
        self._stat_vars["downloaded"].set(stats.bytes_str())

        e = int(stats.elapsed())
        h, rem = divmod(e, 3600)
        m, s   = divmod(rem, 60)
        self._stat_vars["elapsed"].set(
            f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")
        )

        if not stats.running and not self._blink_job:
            if stats.end_time:
                self._stat_vars["status"].set("++ COMPLETE ++")
            else:
                self._stat_vars["status"].set("-- STANDBY --")

    # ─────────────────────────────────────────────────────────── sites tab ───

    def _refresh_sites(self):
        self._sites_lb.delete(0, tk.END)
        data_dir = os.path.expanduser(self._data_dir_var.get().strip() or "../temp_data")
        if not os.path.isdir(data_dir):
            return
        sites = sorted(
            d for d in os.listdir(data_dir)
            if os.path.isdir(os.path.join(data_dir, d))
        )
        for s in sites:
            self._sites_lb.insert(tk.END, s)

    def _on_site_selected(self, _event=None):
        sel = self._sites_lb.curselection()
        if not sel:
            return
        domain   = self._sites_lb.get(sel[0])
        data_dir = os.path.expanduser(self._data_dir_var.get().strip() or "../temp_data")
        self._load_site_tree(domain, os.path.join(data_dir, domain))

    def _load_site_tree(self, domain: str, site_dir: str):
        try:
            all_files  = list(Path(site_dir).rglob("*"))
            file_count = sum(1 for f in all_files if f.is_file())
            total_size = sum(f.stat().st_size for f in all_files if f.is_file())
            self._site_info_var.set(
                f"{domain}   //   {file_count} files   {_fmt_bytes(total_size)}"
            )
        except Exception:
            self._site_info_var.set(domain)

        self._tree.delete(*self._tree.get_children())
        root_node = self._tree.insert(
            "", tk.END, text=f"[ {domain} ]", open=True, values=(site_dir,))
        self._populate_tree_node(root_node, site_dir)

    def _populate_tree_node(self, parent: str, dir_path: str):
        try:
            entries = sorted(
                os.scandir(dir_path),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.is_dir():
                node = self._tree.insert(
                    parent, tk.END, text=f"/{entry.name}",
                    open=False, values=(entry.path,))
                self._tree.insert(node, tk.END, text="", values=("__placeholder__",))
            else:
                self._tree.insert(parent, tk.END,
                                   text=entry.name, values=(entry.path,))

    def _on_tree_expand(self, _event=None):
        node = self._tree.focus()
        children = self._tree.get_children(node)
        if len(children) == 1:
            child = children[0]
            if self._tree.set(child, "path") == "__placeholder__":
                self._tree.delete(child)
                dir_path = self._tree.set(node, "path")
                if dir_path and os.path.isdir(dir_path):
                    self._populate_tree_node(node, dir_path)

    def _on_tree_dblclick(self, _event=None):
        node = self._tree.focus()
        if not node:
            return
        path = self._tree.set(node, "path")
        if path and os.path.isfile(path):
            webbrowser.open(Path(path).as_uri())

    def _open_in_browser(self):
        sel = self._sites_lb.curselection()
        if not sel:
            messagebox.showinfo("NO TARGET SELECTED",
                                "Select a site from the index first.")
            return
        domain   = self._sites_lb.get(sel[0])
        data_dir = os.path.expanduser(self._data_dir_var.get().strip() or "../temp_data")
        index    = os.path.join(data_dir, domain, "index.html")
        if os.path.isfile(index):
            webbrowser.open(Path(index).as_uri())
        else:
            messagebox.showwarning(
                "NOT FOUND",
                f"No index.html at:\n{index}\n\nTry double-clicking a file in the tree.",
            )

    # ──────────────────────────────────────────────────────── update loop ────

    def _schedule_poll(self):
        self.root.after(_POLL_MS, self._poll_updates)

    def _poll_updates(self):
        try:
            while True:
                kind, data = self._update_queue.get_nowait()
                if kind == "stats":
                    self._apply_stats(data)
                elif kind == "log":
                    self._append_log(data)
                elif kind == "complete":
                    self._stop_blink()
                    self._start_btn.configure(state=tk.NORMAL)
                    self._stop_btn.configure(state=tk.DISABLED)
                    self._stat_vars["status"].set("++ COMPLETE ++")
                    self._append_log("=== CRAWL COMPLETE ===")
                    self._refresh_sites()
        except queue.Empty:
            pass
        self._schedule_poll()

    def run(self):
        self._refresh_sites()
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────── helpers ────

def _fmt_bytes(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"
