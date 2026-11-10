#!/usr/bin/env python3
"""
PackMerge - combine several .mcaddon / .mcpack files into ONE .mcaddon,
so Minecraft Bedrock imports all of them in a single launch.

Copyright (C) 2026 NullHarp
https://github.com/nullifiedharp/PackMerge

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file.

The installer sets up the right-click menu for you. Running from source instead:
    python packmerge.py --install      adds "Merge into one .mcaddon" to the right-click menu
    python packmerge.py --uninstall    removes it again

Use:
    Ctrl+click several .mcaddon/.mcpack files in Explorer -> right-click ->
    "Merge into one .mcaddon". A window opens with all of them listed; hit Merge.

Other ways to run:
    python packmerge.py                              open the window empty (Add files...)
    python packmerge.py a.mcaddon b.mcaddon          open the window prefilled
    python packmerge.py --cli OUT.mcaddon IN1 IN2 ...   merge without a window

When running from source, the right-click entry points at this file's current
location, so if you move it, run --install again.
"""
import io
import json
import os
import re
import sys
import threading
import time
import uuid
import queue
import zipfile
from datetime import datetime
from pathlib import Path

__version__ = "1.0.0"
APP = "PackMerge"
VERB_KEY = "PackMerge"
LEGACY_VERB_KEYS = ("McaddonMerger",)  # name used by the pre-release script
VERB_TEXT = "Merge into one .mcaddon"
EXTS = (".mcaddon", ".mcpack")
QUEUE_DIR = Path(os.environ.get("TEMP", os.getcwd())) / "packmerge_queue"
MUTEX_NAME = "Local\\PackMergeCollector"

# manifest module type -> short tag used in the merged folder names
KIND_TAG = {
    "resources": "RP",
    "data": "BP",
    "script": "BP",
    "client_data": "BP",
    "skin_pack": "Skins",
    "world_template": "World",
}


# ----------------------------------------------------------------------------
# Merge engine
# ----------------------------------------------------------------------------
class Pack:
    def __init__(self, name, uid, version, kind, files, source):
        self.name = name          # display name
        self.uid = uid            # header uuid (lowercase) or ""
        self.version = version    # tuple of ints
        self.kind = kind          # RP / BP / Skins / World / Pack
        self.files = files        # list of (relative_path, bytes)
        self.source = source      # where it came from, for the log


def _strip_json_comments(text):
    """Remove // and /* */ comments outside of strings (Bedrock manifests often have them)."""
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] not in "\r\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def loads_lenient(raw):
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        pass
    text = _strip_json_comments(text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)  # trailing commas
    return json.loads(text)


def _ver(v):
    if isinstance(v, (list, tuple)):
        parts = v
    elif isinstance(v, str):
        parts = re.findall(r"\d+", v)
    else:
        return (0,)
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except (TypeError, ValueError):
            out.append(0)
    return tuple(out) or (0,)


def _fmt_ver(t):
    return ".".join(str(x) for x in t)


def _clean_name(name, fallback):
    if isinstance(name, str):
        n = re.sub(r"§.", "", name).strip()
        # "pack.name" is a translation key, not a real name
        if n and not n.lower().startswith("pack."):
            return n
    return fallback or "Pack"


def _safe(name, limit=60):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (s[:limit].strip(" .")) or "Pack"


def _collect(zf, label, fallback_stem, packs, extras, log, depth=0):
    """Find every pack (folder with a manifest.json) in an open zip, recursing into nested archives."""
    entries = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        n = info.filename.replace("\\", "/").lstrip("/")
        parts = n.split("/")
        if not n or "__MACOSX" in parts or parts[-1] == ".DS_Store" or ".." in parts:
            continue
        entries[n] = info

    # pack roots = directories holding a manifest.json, keeping only the outermost ones
    prefixes = sorted(
        {n[: -len("manifest.json")] for n in entries
         if n == "manifest.json" or n.endswith("/manifest.json")},
        key=len,
    )
    roots = []
    for p in prefixes:
        if not any(p.startswith(r) for r in roots):
            roots.append(p)

    claimed = set()
    for r in roots:
        members = [n for n in entries if n.startswith(r)]
        claimed.update(members)
        files = [(n[len(r):], zf.read(entries[n])) for n in members]
        try:
            man = loads_lenient(zf.read(entries[r + "manifest.json"]))
            if not isinstance(man, dict):
                man = {}
        except Exception as e:
            log(f"  ! couldn't read manifest in {label}/{r or '(root)'}: {e}")
            man = {}
        header = man.get("header") if isinstance(man.get("header"), dict) else {}
        kind = "Pack"
        for m in man.get("modules") or []:
            if isinstance(m, dict) and m.get("type") in KIND_TAG:
                kind = KIND_TAG[m["type"]]
                if kind in ("RP", "BP"):
                    break
        folder = r.rstrip("/").split("/")[-1] if r else fallback_stem
        packs.append(Pack(
            name=_clean_name(header.get("name"), folder),
            uid=str(header.get("uuid", "")).strip().lower(),
            version=_ver(header.get("version")),
            kind=kind,
            files=files,
            source=label,
        ))

    for n, info in entries.items():
        if n in claimed:
            continue
        low = n.lower()
        if low.endswith((".mcpack", ".mcaddon", ".zip")):
            if depth >= 4:
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(zf.read(info))) as inner:
                    _collect(inner, f"{label}/{n}", Path(n).stem, packs, extras, log, depth + 1)
            except zipfile.BadZipFile:
                log(f"  ! {label}/{n} is not a valid archive, skipped")
        elif low.endswith((".mcworld", ".mctemplate")):
            extras.append((Path(n).name, zf.read(info), label))


def merge(inputs, output, log=print):
    """Merge input .mcaddon/.mcpack files into one .mcaddon. Returns (packs_written, extras_written)."""
    output = Path(output)
    in_resolved = {Path(p).resolve() for p in inputs}
    if output.resolve() in in_resolved:
        raise RuntimeError("The output file is one of the inputs - pick a different name.")

    packs, extras = [], []
    for p in inputs:
        p = Path(p)
        log(f"Reading {p.name}")
        before_p, before_e = len(packs), len(extras)
        try:
            with zipfile.ZipFile(p) as zf:
                _collect(zf, p.name, p.stem, packs, extras, log)
        except (zipfile.BadZipFile, OSError) as e:
            log(f"  ! skipped ({e})")
            continue
        found = len(packs) - before_p
        extra = len(extras) - before_e
        msg = f"  found {found} pack(s)"
        if extra:
            msg += f" + {extra} world/template file(s)"
        if not found and not extra:
            msg = "  ! no packs found inside"
        log(msg)

    if not packs and not extras:
        raise RuntimeError("No packs were found in the selected files.")

    # de-duplicate by manifest uuid, keeping the newest version
    chosen, order = {}, []
    for pk in packs:
        key = pk.uid or f"no-uuid:{id(pk)}"
        if key not in chosen:
            chosen[key] = pk
            order.append(key)
            continue
        old = chosen[key]
        if pk.version > old.version:
            log(f"  ^ {pk.name}: using v{_fmt_ver(pk.version)} instead of v{_fmt_ver(old.version)}")
            chosen[key] = pk
        else:
            log(f"  = {pk.name} v{_fmt_ver(pk.version)} appears more than once, kept one copy")

    used = set()

    def unique(base):
        name, i = base, 2
        while name.lower() in used:
            name = f"{base}_{i}"
            i += 1
        used.add(name.lower())
        return name

    tmp = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for key in order:
            pk = chosen[key]
            folder = unique(f"{_safe(pk.name)}_{pk.kind}")
            for rel, data in pk.files:
                z.writestr(f"{folder}/{rel}", data)
        for fname, data, _src in extras:
            stem, ext = os.path.splitext(fname)
            z.writestr(unique(_safe(stem)) + ext, data)
    os.replace(tmp, output)

    log(f"\nWrote {output.name}: {len(order)} pack(s)"
        + (f", {len(extras)} world/template file(s)" if extras else ""))
    for key in order:
        pk = chosen[key]
        log(f"  - [{pk.kind}] {pk.name}  v{_fmt_ver(pk.version)}")
    return len(order), len(extras)


# ----------------------------------------------------------------------------
# Explorer multi-select collector
# ----------------------------------------------------------------------------
def collect_selection(path):
    """Explorer starts one process per selected file. Each drops its path in a queue
    folder; the first process (mutex owner) waits for the rest and gathers them.
    Returns the full list for the leader, or None for the followers (who just exit)."""
    import ctypes
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    (QUEUE_DIR / f"{uuid.uuid4().hex}.txt").write_text(path, encoding="utf-8")

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k32.CreateMutexW(None, True, MUTEX_NAME)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS -> another process is collecting
        k32.CloseHandle(handle)
        return None

    paths = []
    try:
        start = last_change = time.time()
        last = -1
        while time.time() - start < 20:
            n = sum(1 for _ in QUEUE_DIR.glob("*.txt"))
            now = time.time()
            if n != last:
                last, last_change = n, now
            elif now - last_change >= 1.5 and now - start >= 2.0:
                break
            time.sleep(0.15)
        for f in QUEUE_DIR.glob("*.txt"):
            try:
                age = time.time() - f.stat().st_mtime
                p = f.read_text(encoding="utf-8").strip()
                f.unlink()
                if p and age < 120:  # ignore leftovers from an old crashed run
                    paths.append(p)
            except OSError:
                pass
    finally:
        k32.CloseHandle(handle)
    return sorted(set(paths), key=lambda s: Path(s).name.lower())


# ----------------------------------------------------------------------------
# Right-click menu install / uninstall (current user only, no admin needed)
# ----------------------------------------------------------------------------
def _launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    if pyw.exists():
        exe = pyw
    return f'"{exe}" "{Path(__file__).resolve()}" "%1"'


def resource_path(rel):
    """Find bundled files both from source and inside a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / rel


def _verb_base(ext, key=VERB_KEY):
    return rf"Software\Classes\SystemFileAssociations\{ext}\shell\{key}"


def _delete_verb(winreg, ext, key):
    base = _verb_base(ext, key)
    for k in (base + r"\command", base):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, k)
        except FileNotFoundError:
            pass


def _notify_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def is_installed():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _verb_base(EXTS[0]) + r"\command"):
            return True
    except (OSError, ImportError):
        return False


def install():
    import winreg
    cmd = _launch_command()
    icon = None
    if getattr(sys, "frozen", False):
        icon = f'"{sys.executable}",0'
    elif resource_path("assets/icon.ico").exists():
        icon = str(resource_path("assets/icon.ico"))
    for ext in EXTS:
        for old in LEGACY_VERB_KEYS:
            _delete_verb(winreg, ext, old)
        base = _verb_base(ext)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, VERB_TEXT)
            if icon:
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
            # "Player" keeps the entry visible when more than 15 files are selected
            winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    _notify_shell()


def uninstall():
    import winreg
    for ext in EXTS:
        for key in (VERB_KEY,) + LEGACY_VERB_KEYS:
            _delete_verb(winreg, ext, key)
    _notify_shell()


# ----------------------------------------------------------------------------
# Window
# ----------------------------------------------------------------------------
BG = "#1e1e1e"
PANEL = "#252526"
FIELD = "#2d2d30"
FG = "#d4d4d4"
MUTED = "#8a8a8a"
ACCENT = "#3c8527"      # Minecraft-ish green
ACCENT_HI = "#52a535"
BTN = "#3a3a3d"
BTN_HI = "#4a4a4e"


def run_gui(initial_files):
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title(f"{APP} {__version__}")
    root.configure(bg=BG)
    try:
        ico = resource_path("assets/icon.ico")
        if os.name == "nt" and ico.exists():
            root.iconbitmap(default=str(ico))
        else:
            png = resource_path("assets/icon.png")
            if png.exists():
                root._icon_img = tk.PhotoImage(file=str(png))
                root.iconphoto(True, root._icon_img)
    except Exception:
        pass
    root.geometry("680x560")
    root.minsize(540, 440)

    files = []
    log_q = queue.Queue()
    state = {"user_output": False, "busy": False}

    def button(parent, text, cmd, primary=False):
        b = tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, cursor="hand2",
                      bg=ACCENT if primary else BTN, fg="white",
                      activebackground=ACCENT_HI if primary else BTN_HI, activeforeground="white",
                      font=("Segoe UI", 11 if primary else 9, "bold" if primary else "normal"),
                      padx=14, pady=8 if primary else 4)
        return b

    tk.Label(root, text="Merge Minecraft add-ons into one .mcaddon", bg=BG, fg=FG,
             font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
    tk.Label(root, text="Packs are pulled out of every file, duplicates are dropped (newest version wins), "
                        "and everything goes into one file Minecraft imports in one go.",
             bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=640, justify="left").pack(anchor="w", padx=14)

    # file list
    list_frame = tk.Frame(root, bg=BG)
    list_frame.pack(fill="both", expand=True, padx=14, pady=(10, 4))
    lb = tk.Listbox(list_frame, bg=PANEL, fg=FG, selectbackground=ACCENT, selectforeground="white",
                    highlightthickness=0, bd=0, activestyle="none", font=("Segoe UI", 10),
                    selectmode="extended")
    sb = tk.Scrollbar(list_frame, command=lb.yview, bg=PANEL, troughcolor=BG, bd=0)
    lb.config(yscrollcommand=sb.set)
    lb.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    row = tk.Frame(root, bg=BG)
    row.pack(fill="x", padx=14)
    count_lbl = tk.Label(row, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))

    # output
    out_var = tk.StringVar()
    out_row = tk.Frame(root, bg=BG)
    out_row.pack(fill="x", padx=14, pady=(8, 0))
    tk.Label(out_row, text="Save as", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
    out_entry = tk.Entry(out_row, textvariable=out_var, bg=FIELD, fg=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 9))
    out_entry.pack(side="left", fill="x", expand=True, padx=8, ipady=4)
    out_entry.bind("<Key>", lambda e: state.update(user_output=True))

    def default_output():
        if not files:
            return ""
        folder = Path(files[0]).parent
        stamp = datetime.now().strftime("%Y-%m-%d %H%M")
        cand = folder / f"Merged {len(files)} addons {stamp}.mcaddon"
        i = 2
        while cand.exists():
            cand = folder / f"Merged {len(files)} addons {stamp} ({i}).mcaddon"
            i += 1
        return str(cand)

    def refresh():
        lb.delete(0, "end")
        for f in files:
            lb.insert("end", "  " + Path(f).name)
        count_lbl.config(text=f"{len(files)} file(s)")
        if not state["user_output"]:
            out_var.set(default_output())

    def add_paths(paths):
        seen = {os.path.normcase(os.path.abspath(f)) for f in files}
        for p in paths:
            if p.lower().endswith(EXTS):
                key = os.path.normcase(os.path.abspath(p))
                if key not in seen:
                    seen.add(key)
                    files.append(os.path.abspath(p))
        refresh()

    def add_files():
        picked = filedialog.askopenfilenames(
            title="Choose add-ons", filetypes=[("Minecraft add-ons", "*.mcaddon *.mcpack"), ("All files", "*.*")])
        add_paths(picked)

    def remove_selected():
        for i in reversed(lb.curselection()):
            files.pop(i)
        refresh()

    def clear():
        files.clear()
        refresh()

    def browse_out():
        start = Path(out_var.get()).parent if out_var.get() else Path.home()
        p = filedialog.asksaveasfilename(title="Save merged add-on as", defaultextension=".mcaddon",
                                         initialdir=str(start), initialfile=Path(out_var.get()).name or "Merged.mcaddon",
                                         filetypes=[("Minecraft add-on", "*.mcaddon")])
        if p:
            out_var.set(p)
            state["user_output"] = True

    button(row, "Add files...", add_files).pack(side="left")
    button(row, "Remove selected", remove_selected).pack(side="left", padx=6)
    button(row, "Clear", clear).pack(side="left")
    count_lbl.pack(side="right")
    button(out_row, "Browse...", browse_out).pack(side="left")
    lb.bind("<Delete>", lambda e: remove_selected())

    open_var = tk.BooleanVar(value=True)
    act_row = tk.Frame(root, bg=BG)
    act_row.pack(fill="x", padx=14, pady=10)
    tk.Checkbutton(act_row, text="Import into Minecraft when done", variable=open_var,
                   bg=BG, fg=FG, selectcolor=FIELD, activebackground=BG, activeforeground=FG,
                   font=("Segoe UI", 9), bd=0, highlightthickness=0).pack(side="left")
    merge_btn = button(act_row, "Merge", lambda: start_merge(), primary=True)
    merge_btn.pack(side="right")

    # log
    log_box = tk.Text(root, height=9, bg=PANEL, fg=FG, relief="flat", bd=0, font=("Consolas", 9),
                      wrap="word", state="disabled", padx=8, pady=6)
    log_box.pack(fill="both", expand=False, padx=14, pady=(0, 6))

    def write_log(msg):
        log_box.config(state="normal")
        log_box.insert("end", msg + "\n")
        log_box.see("end")
        log_box.config(state="disabled")

    # context-menu status bar
    status_row = tk.Frame(root, bg=BG)
    status_row.pack(fill="x", padx=14, pady=(0, 10))
    status_lbl = tk.Label(status_row, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
    status_lbl.pack(side="left")
    toggle_btn = button(status_row, "", lambda: toggle_menu())
    toggle_btn.pack(side="right")

    def refresh_status():
        if os.name != "nt":
            status_lbl.config(text="Right-click menu: Windows only")
            toggle_btn.pack_forget()
            return
        if is_installed():
            status_lbl.config(text='Right-click menu: installed ("Merge into one .mcaddon")')
            toggle_btn.config(text="Remove from right-click menu")
        else:
            status_lbl.config(text="Right-click menu: not installed")
            toggle_btn.config(text="Add to right-click menu")

    def toggle_menu():
        try:
            if is_installed():
                uninstall()
                write_log("Removed the right-click menu entry.")
            else:
                install()
                write_log('Added "Merge into one .mcaddon" to the right-click menu for .mcaddon and .mcpack files.')
        except Exception as e:
            messagebox.showerror(APP, f"Couldn't change the right-click menu:\n{e}")
        refresh_status()

    def start_merge():
        if state["busy"]:
            return
        if len(files) < 1:
            messagebox.showinfo(APP, "Add some .mcaddon or .mcpack files first.")
            return
        out = out_var.get().strip()
        if not out:
            messagebox.showinfo(APP, "Choose where to save the merged file.")
            return
        if not out.lower().endswith(".mcaddon"):
            out += ".mcaddon"
            out_var.set(out)
        if Path(out).exists() and not messagebox.askyesno(APP, f"{Path(out).name} already exists. Replace it?"):
            return
        state["busy"] = True
        merge_btn.config(state="disabled", text="Merging...")
        log_box.config(state="normal")
        log_box.delete("1.0", "end")
        log_box.config(state="disabled")
        do_open = open_var.get()

        def work():
            try:
                merge(list(files), out, log=lambda m: log_q.put(("log", m)))
                log_q.put(("done", (out, do_open)))
            except Exception as e:
                log_q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def pump():
        try:
            while True:
                kind, payload = log_q.get_nowait()
                if kind == "log":
                    write_log(payload)
                else:
                    state["busy"] = False
                    merge_btn.config(state="normal", text="Merge")
                    if kind == "error":
                        write_log(f"\nFailed: {payload}")
                        messagebox.showerror(APP, payload)
                    else:
                        out, do_open = payload
                        state["user_output"] = False
                        if do_open:
                            write_log("Opening in Minecraft...")
                            try:
                                os.startfile(out)
                            except Exception as e:
                                write_log(f"  ! couldn't open it automatically ({e}) - double-click the file instead")
        except queue.Empty:
            pass
        root.after(100, pump)

    add_paths(initial_files)
    refresh_status()
    pump()
    root.mainloop()


# ----------------------------------------------------------------------------
def main(argv):
    if "--version" in argv:
        print(f"{APP} {__version__}")
        return
    if "--install" in argv:
        install()
        print(f'Installed. Select .mcaddon/.mcpack files, right-click -> "{VERB_TEXT}".')
        return
    if "--uninstall" in argv:
        uninstall()
        print("Removed the right-click menu entry.")
        return
    if argv and argv[0] == "--cli":
        if len(argv) < 3:
            print("usage: packmerge.py --cli OUTPUT.mcaddon INPUT1 [INPUT2 ...]")
            sys.exit(2)
        merge(argv[2:], argv[1])
        return

    paths = [a for a in argv if a.lower().endswith(EXTS)]
    if len(paths) == 1 and os.name == "nt":
        # probably one of several processes Explorer started for a multi-select
        paths = collect_selection(os.path.abspath(paths[0]))
        if paths is None:
            return
    run_gui(paths)


if __name__ == "__main__":
    main(sys.argv[1:])
