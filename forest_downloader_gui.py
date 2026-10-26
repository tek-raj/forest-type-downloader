#!/usr/bin/env python3
"""
Forest Type Downloader - a small window around cdse_download.py.

Pick the reference year(s), enter a CDSE (dataspace.copernicus.eu) login and
press Download. Tiles are saved as GeoTIFFs in <folder>/<year>/.
The password is only kept in memory while the window is open; the email is
remembered for next time.
"""

import json
import os
import queue
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cdse_download as cd

YEARS = ["2018", "2021", "2024"]
SETTINGS = Path.home() / ".forest_type_downloader.json"
DEFAULT_OUT = Path.home() / "Downloads" / "Forest_Type"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(d: dict) -> None:
    try:
        SETTINGS.write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    elif os.name == "nt":
        os.startfile(path)
    else:
        subprocess.run(["xdg-open", str(path)])


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.tiles = None
        settings = load_settings()

        root.title("Forest Type Downloader")
        root.resizable(False, False)
        f = ttk.Frame(root, padding=16)
        f.grid(sticky="nsew")

        ttk.Label(f, text="Copernicus Forest Type, 10 m, whole of Europe",
                  font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Downloads from the Copernicus Data Space Ecosystem (free account).",
                  foreground="gray").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

        # Login
        ttk.Label(f, text="Email:").grid(row=2, column=0, sticky="w")
        self.user = tk.StringVar(value=settings.get("user", ""))
        ttk.Entry(f, textvariable=self.user, width=38).grid(row=2, column=1, columnspan=2, sticky="we", pady=2)
        ttk.Label(f, text="Password:").grid(row=3, column=0, sticky="w")
        self.pw = tk.StringVar()
        self.pw_entry = ttk.Entry(f, textvariable=self.pw, show="•", width=38)
        self.pw_entry.grid(row=3, column=1, columnspan=2, sticky="we", pady=2)
        self.show_pw = tk.BooleanVar()
        ttk.Checkbutton(f, text="Show password", variable=self.show_pw,
                        command=lambda: self.pw_entry.config(show="" if self.show_pw.get() else "•")
                        ).grid(row=4, column=1, sticky="w")

        # Years
        ttk.Label(f, text="Year(s):").grid(row=5, column=0, sticky="nw", pady=(12, 0))
        self.year_vars, self.year_labels = {}, {}
        for i, y in enumerate(YEARS):
            v = tk.BooleanVar(value=(y == "2024"))
            cb = ttk.Checkbutton(f, text=y, variable=v, command=self.update_estimate)
            cb.grid(row=5 + i, column=1, sticky="w", pady=(12 if i == 0 else 0, 0))
            self.year_vars[y] = v
            self.year_labels[y] = ttk.Label(f, text="", foreground="gray")
            self.year_labels[y].grid(row=5 + i, column=2, sticky="w", pady=(12 if i == 0 else 0, 0))
        self.estimate = ttk.Label(f, text="Loading tile list...", foreground="gray")
        self.estimate.grid(row=8, column=1, columnspan=2, sticky="w")

        # Output folder
        ttk.Label(f, text="Save to:").grid(row=9, column=0, sticky="w", pady=(12, 0))
        self.out = tk.StringVar(value=settings.get("out", str(DEFAULT_OUT)))
        ttk.Entry(f, textvariable=self.out, width=30).grid(row=9, column=1, sticky="we", pady=(12, 0))
        ttk.Button(f, text="Choose...", command=self.choose_out).grid(row=9, column=2, sticky="w",
                                                                      padx=(6, 0), pady=(12, 0))

        # Buttons + progress
        bf = ttk.Frame(f)
        bf.grid(row=10, column=0, columnspan=3, sticky="we", pady=(16, 6))
        self.go = ttk.Button(bf, text="Download", command=self.start)
        self.go.pack(side="left")
        self.stop_btn = ttk.Button(bf, text="Stop", command=self.request_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(bf, text="Open folder", command=lambda: open_folder(Path(self.out.get()))).pack(side="right")

        self.bar = ttk.Progressbar(f, length=420, mode="determinate")
        self.bar.grid(row=11, column=0, columnspan=3, sticky="we")
        self.status = ttk.Label(f, text="Ready.")
        self.status.grid(row=12, column=0, columnspan=3, sticky="w", pady=(4, 0))

        threading.Thread(target=self.load_catalogue, daemon=True).start()
        root.after(200, self.poll)

    # ---------------------------------------------------------------- UI
    def choose_out(self):
        d = filedialog.askdirectory(initialdir=self.out.get() or str(Path.home()))
        if d:
            self.out.set(d)

    def selected_years(self) -> list:
        return [y for y, v in self.year_vars.items() if v.get()]

    def update_estimate(self):
        if self.tiles is None:
            return
        sel = cd.select(self.tiles, self.selected_years(), None)
        self.estimate.config(text=f"Selected: {len(sel)} tiles, {sum(t['size'] for t in sel)/1e9:.1f} GB")

    def set_running(self, running: bool):
        self.go.config(state="disabled" if running else "normal")
        self.stop_btn.config(state="normal" if running else "disabled")

    def start(self):
        user, pw, years = self.user.get().strip(), self.pw.get(), self.selected_years()
        if not user or not pw:
            messagebox.showwarning("Login needed", "Please enter the email and password of your "
                                   "Copernicus Data Space account (dataspace.copernicus.eu).")
            return
        if not years:
            messagebox.showwarning("No year", "Please tick at least one year.")
            return
        if self.tiles is None:
            messagebox.showinfo("Please wait", "Still loading the tile list - try again in a moment.")
            return
        out = Path(self.out.get()).expanduser()
        save_settings({"user": user, "out": str(out)})
        self.stop.clear()
        self.set_running(True)
        self.status.config(text="Logging in...")
        self.worker = threading.Thread(target=self.run, args=(user, pw, years, out), daemon=True)
        self.worker.start()

    def request_stop(self):
        self.stop.set()
        self.stop_btn.config(state="disabled")
        self.status.config(text="Stopping after the tiles in progress...")

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "catalogue":
                    for y in YEARS:
                        sel = cd.select(self.tiles, [y], None)
                        self.year_labels[y].config(
                            text=f"{len(sel)} tiles, {sum(t['size'] for t in sel)/1e9:.1f} GB")
                    self.update_estimate()
                elif kind == "catalogue_error":
                    self.estimate.config(text="Could not load the tile list - check the internet "
                                              "connection and restart.", foreground="red")
                elif kind == "start":
                    self.bar.config(maximum=msg[1], value=0)
                    self.status.config(text=f"Downloading {msg[1]} tiles...")
                elif kind == "progress":
                    _, i, n, failed = msg
                    self.bar.config(value=i)
                    extra = f", {failed} failed" if failed else ""
                    self.status.config(text=f"{i} of {n} tiles done{extra}")
                elif kind == "error":
                    self.set_running(False)
                    self.status.config(text="Stopped.")
                    messagebox.showerror("Problem", msg[1])
                elif kind == "done":
                    _, ok, failed, stopped, out = msg
                    self.set_running(False)
                    if stopped:
                        text = f"Stopped. {ok} tiles saved. Press Download again to continue."
                    elif failed:
                        text = f"{ok} tiles saved, {failed} failed. Press Download again to retry them."
                    else:
                        text = f"Finished: all {ok} tiles saved."
                    self.status.config(text=text)
                    if not stopped:
                        if messagebox.askyesno("Download finished", text + "\n\nOpen the folder?"):
                            open_folder(out)
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    # ------------------------------------------------------------ worker
    def load_catalogue(self):
        try:
            self.tiles = cd.load_tiles()
            self.q.put(("catalogue",))
        except Exception:
            self.q.put(("catalogue_error",))

    def run(self, user, pw, years, out):
        try:
            auth = cd.CDSE(user, pw)
        except Exception as e:
            self.q.put(("error", str(e)))
            return
        tiles = cd.select(self.tiles, years, None)
        self.q.put(("start", len(tiles)))
        ok = failed = done = 0
        pool = ThreadPoolExecutor(max_workers=4)
        futs = [pool.submit(cd.fetch, auth, t, out) for t in tiles]
        try:
            for fut in as_completed(futs):
                if self.stop.is_set():
                    break
                if fut.result().startswith("FAILED"):
                    failed += 1
                else:
                    ok += 1
                done += 1
                self.q.put(("progress", done, len(tiles), failed))
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        self.q.put(("done", ok, failed, self.stop.is_set(), out))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
