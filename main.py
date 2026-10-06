
---

# 📄 `venv_manager.py` — English version (full source)

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🐍 venv_manager.py — Python Virtual Environment Manager (English UI)

Single-file Tkinter GUI for managing Python virtual environments
on Windows, Linux, and macOS. Includes a built-in code editor and
a script runner with live output.
"""

import os
import shutil
import subprocess
import threading
import venv
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext


# =========================================================
#  PLATFORM HELPERS
# =========================================================
WINDOWS = os.name == "nt"


def python_exe(env_path: Path) -> Path:
    return env_path / ("Scripts/python.exe" if WINDOWS else "bin/python")


def activate_cmd(name: str) -> str:
    return f"{name}\\Scripts\\activate" if WINDOWS else f"source {name}/bin/activate"


def is_valid_env(path: Path) -> bool:
    return python_exe(path).exists()


def python_version(env_path: Path) -> str:
    try:
        r = subprocess.run(
            [str(python_exe(env_path)), "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip().replace("Python ", "")
    except Exception:
        return "?"


def folder_size(path: Path) -> str:
    try:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        for unit in ["B", "KB", "MB", "GB"]:
            if total < 1024:
                return f"{total:.1f}{unit}"
            total /= 1024
        return f"{total:.1f}TB"
    except Exception:
        return "?"


def find_envs(folder: Path) -> list:
    if not folder.exists():
        return []
    return [p for p in folder.iterdir() if p.is_dir() and is_valid_env(p)]


# =========================================================
#  MAIN APP
# =========================================================
class VenvManagerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🐍 Python Virtual Environment Manager")
        self.root.geometry("1100x720")
        self.root.minsize(950, 620)

        self.work_dir = tk.StringVar(value=str(Path.cwd()))
        self.busy = False

        # Editor / runner state
        self.editor_file = tk.StringVar(value="")
        self.running_proc = None
        self.run_env = tk.StringVar(value="")
        self.run_file = tk.StringVar(value="")

        self._setup_style()
        self._build_ui()

    # -----------------------------------------------------
    #  STYLE
    # -----------------------------------------------------
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TNotebook.Tab", padding=[16, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", "#ffffff"), ("!selected", "#e1e5ea")],
                  foreground=[("selected", "#0d6efd"), ("!selected", "#333")])
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"), foreground="#0d6efd")
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#666")
        style.configure("Green.TButton", foreground="white", background="#198754")
        style.map("Green.TButton", background=[("active", "#157347")])
        style.configure("Red.TButton", foreground="white", background="#dc3545")
        style.map("Red.TButton", background=[("active", "#bb2d3b")])
        style.configure("Blue.TButton", foreground="white", background="#0d6efd")
        style.map("Blue.TButton", background=[("active", "#0b5ed7")])
        style.configure("Orange.TButton", foreground="white", background="#fd7e14")
        style.map("Orange.TButton", background=[("active", "#e36a06")])
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    # -----------------------------------------------------
    #  MAIN WINDOW
    # -----------------------------------------------------
    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self.root, padding=(12, 10))
        top.pack(fill="x")
        ttk.Label(top, text="🐍 Virtual Environment Manager", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="Working directory:").pack(side="left", padx=(24, 4))
        ttk.Entry(top, textvariable=self.work_dir, width=50).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="📁 Browse", command=self._pick_dir).pack(side="left", padx=4)
        ttk.Button(top, text="🔄 Refresh", command=self._refresh_all).pack(side="left")

        ttk.Separator(self.root).pack(fill="x")

        # Status bar (BEFORE tabs, because tab setup calls refresh)
        self.status = tk.StringVar(value="Ready.")
        bottom = ttk.Frame(self.root, padding=(10, 4))
        bottom.pack(fill="x", side="bottom")
        ttk.Separator(self.root).pack(fill="x", side="bottom")
        ttk.Label(bottom, textvariable=self.status, style="Sub.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=180)
        self.progress.pack(side="right")

        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_create = ttk.Frame(self.notebook, padding=10)
        self.tab_envs   = ttk.Frame(self.notebook, padding=14)
        self.tab_run    = ttk.Frame(self.notebook, padding=14)
        self.tab_info   = ttk.Frame(self.notebook, padding=14)
        self.tab_log    = ttk.Frame(self.notebook, padding=14)
        self.tab_help   = ttk.Frame(self.notebook, padding=14)

        self.notebook.add(self.tab_create, text="🆕 Create & Write")
        self.notebook.add(self.tab_envs,   text="📂 Environments")
        self.notebook.add(self.tab_run,    text="▶ Run")
        self.notebook.add(self.tab_info,   text="🔍 Info")
        self.notebook.add(self.tab_log,    text="📜 Log")
        self.notebook.add(self.tab_help,   text="🎓 Help")

        self._build_tab_create()
        self._build_tab_envs()
        self._build_tab_run()
        self._build_tab_info()
        self._build_tab_log()
        self._build_tab_help()

    # =====================================================
    #  TAB: CREATE + EDITOR
    # =====================================================
    def _build_tab_create(self):
        f = self.tab_create

        paned = ttk.Panedwindow(f, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # ---------- LEFT: settings ----------
        left = ttk.Frame(paned, padding=10)
        paned.add(left, weight=1)

        ttk.Label(left, text="Environment name:",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.env_name = tk.StringVar(value=".venv")
        ttk.Entry(left, textvariable=self.env_name, width=30).grid(
            row=0, column=1, sticky="we", pady=(0, 6))

        ttk.Label(left, text="Python (optional):").grid(row=1, column=0, sticky="w", pady=4)
        self.python_path = tk.StringVar(value="")
        ttk.Entry(left, textvariable=self.python_path, width=30).grid(
            row=1, column=1, sticky="we", pady=4)

        self.opt_system_site = tk.BooleanVar(value=False)
        self.opt_upgrade_pip = tk.BooleanVar(value=True)
        self.opt_symlink = tk.BooleanVar(value=not WINDOWS)
        self.opt_clear = tk.BooleanVar(value=False)

        opts = ttk.LabelFrame(left, text="Options", padding=8)
        opts.grid(row=2, column=0, columnspan=2, sticky="we", pady=8)
        ttk.Checkbutton(opts, text="See system packages",
                        variable=self.opt_system_site).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Upgrade pip",
                        variable=self.opt_upgrade_pip).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Use symlinks",
                        variable=self.opt_symlink).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Delete existing and recreate",
                        variable=self.opt_clear).grid(row=3, column=0, sticky="w")

        pk = ttk.LabelFrame(left, text="Packages (space-separated)", padding=8)
        pk.grid(row=3, column=0, columnspan=2, sticky="we", pady=6)
        self.packages = tk.StringVar(value="")
        ttk.Entry(pk, textvariable=self.packages, width=40).pack(fill="x")

        rq = ttk.LabelFrame(left, text="requirements.txt (optional)", padding=8)
        rq.grid(row=4, column=0, columnspan=2, sticky="we", pady=6)
        self.req_file = tk.StringVar(value="")
        ttk.Entry(rq, textvariable=self.req_file).pack(side="left", fill="x", expand=True)
        ttk.Button(rq, text="📄", width=3, command=self._pick_req).pack(side="left", padx=4)

        ttk.Button(left, text="🚀  CREATE VIRTUAL ENVIRONMENT", style="Green.TButton",
                   command=self._create_env_clicked).grid(
            row=5, column=0, columnspan=2, pady=12, sticky="we", ipady=6)

        left.columnconfigure(1, weight=1)

        # ---------- RIGHT: editor ----------
        right = ttk.Frame(paned, padding=10)
        paned.add(right, weight=2)

        eb = ttk.Frame(right)
        eb.pack(fill="x")
        ttk.Label(eb, text="📝 Simple Editor",
                  font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(eb, text="🆕 New", command=self._editor_new).pack(side="right", padx=2)
        ttk.Button(eb, text="📂 Open", command=self._editor_open).pack(side="right", padx=2)
        ttk.Button(eb, text="💾 Save", command=self._editor_save).pack(side="right", padx=2)
        ttk.Button(eb, text="▶ Save & Run", style="Blue.TButton",
                   command=self._editor_save_and_run).pack(side="right", padx=2)

        ttk.Label(right, textvariable=self.editor_file,
                  style="Sub.TLabel").pack(fill="x", pady=(4, 4))

        self.editor = scrolledtext.ScrolledText(
            right, wrap="none", font=("Consolas", 11),
            bg="#fdfdfd", fg="#222", insertbackground="#222",
            undo=True, tabs=("4c",),
        )
        self.editor.pack(fill="both", expand=True)
        self.editor.bind("<Tab>", self._editor_tab)
        self.editor.insert("1.0", self._default_snippet())

    def _editor_tab(self, event):
        self.editor.insert("insert", "    ")
        return "break"

    def _default_snippet(self):
        return (
            "# -*- coding: utf-8 -*-\n"
            "# Sample script. Edit and click '▶ Save & Run'.\n"
            "\n"
            "print('Hello from the virtual environment!')\n"
            "\n"
            "import sys\n"
            "print('Python:', sys.version.split()[0])\n"
            "print('Executable:', sys.executable)\n"
            "\n"
            "input('\\nPress Enter to exit...')\n"
        )

    def _editor_new(self):
        if messagebox.askyesno("New", "Unsaved changes will be lost. Continue?"):
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", self._default_snippet())
            self.editor_file.set("")

    def _editor_open(self):
        path = filedialog.askopenfilename(
            initialdir=self.work_dir.get(),
            filetypes=[("Python", "*.py"), ("All files", "*.*")])
        if path:
            try:
                content = Path(path).read_text(encoding="utf-8")
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", content)
                self.editor_file.set(path)
                self._log(f"📂 Opened: {path}", "info")
            except Exception as e:
                messagebox.showerror("Error", f"Could not open: {e}")

    def _editor_save(self):
        path = self.editor_file.get()
        if not path:
            path = filedialog.asksaveasfilename(
                initialdir=self.work_dir.get(),
                defaultextension=".py",
                filetypes=[("Python", "*.py"), ("All files", "*.*")])
            if not path:
                return None
        try:
            Path(path).write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
            self.editor_file.set(path)
            self._log(f"💾 Saved: {path}", "ok")
            return path
        except Exception as e:
            messagebox.showerror("Error", f"Could not save: {e}")
            return None

    def _editor_save_and_run(self):
        path = self._editor_save()
        if not path:
            return

        name = self.env_name.get().strip() or ".venv"
        env_path = self._work_path() / name

        if not is_valid_env(env_path):
            if not messagebox.askyesno(
                    "Environment Not Found",
                    f"Virtual environment '{name}' not found.\n"
                    f"Create it first?"):
                return
            self._create_env_clicked()
            return

        self.run_env.set(name)
        self.run_file.set(str(path))
        self.notebook.select(self.tab_run)
        self._run_start(name, Path(path))

    # =====================================================
    #  TAB: ENVIRONMENTS
    # =====================================================
    def _build_tab_envs(self):
        f = self.tab_envs

        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Existing virtual environments",
                  font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(top, text="▶ Run in this env", style="Blue.TButton",
                   command=self._envs_run_selected).pack(side="right", padx=4)
        ttk.Button(top, text="🗑️ Delete", style="Red.TButton",
                   command=self._envs_delete_selected).pack(side="right", padx=4)
        ttk.Button(top, text="🔄 Refresh",
                   command=self._refresh_envs).pack(side="right")

        cols = ("name", "python", "size", "created", "path")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        headings = {"name": "Name", "python": "Python", "size": "Size",
                    "created": "Created", "path": "Path"}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=110 if c != "path" else 320, anchor="w")

        sb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, pady=8)
        sb.pack(side="right", fill="y", pady=8)

        self.tree.bind("<Double-1>", lambda e: self._envs_show_info())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._envs_update_selection())

        self.sel_info = tk.StringVar(value="Select an environment.")
        ttk.Label(f, textvariable=self.sel_info, style="Sub.TLabel").pack(side="bottom", fill="x")

        self._refresh_envs()

    def _envs_run_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select an environment first.")
            return
        name = self.tree.item(sel[0], "values")[0]
        self.run_env.set(name)
        self.notebook.select(self.tab_run)

    # =====================================================
    #  TAB: RUN
    # =====================================================
    def _build_tab_run(self):
        f = self.tab_run

        ttk.Label(f, text="▶  Python Script Runner",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")

        panel = ttk.LabelFrame(f, text="Controls", padding=10)
        panel.pack(fill="x", pady=8)

        ttk.Label(panel, text="Environment:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.cb_run_env = ttk.Combobox(
            panel, textvariable=self.run_env, width=25, state="readonly")
        self.cb_run_env.grid(row=0, column=1, sticky="w", padx=(0, 8))

        ttk.Label(panel, text="Script:").grid(row=0, column=2, sticky="w", padx=(8, 6))
        ttk.Entry(panel, textvariable=self.run_file, width=40).grid(
            row=0, column=3, sticky="we", padx=(0, 6))
        ttk.Button(panel, text="📄", width=3,
                   command=self._run_pick_file).grid(row=0, column=4)

        btn = ttk.Frame(panel)
        btn.grid(row=1, column=0, columnspan=5, sticky="we", pady=(10, 0))
        self.btn_start = ttk.Button(btn, text="▶ START", style="Green.TButton",
                                    command=self._run_start_clicked)
        self.btn_start.pack(side="left", padx=2, ipadx=12)
        self.btn_stop = ttk.Button(btn, text="⏹ STOP", style="Red.TButton",
                                   command=self._run_stop_clicked, state="disabled")
        self.btn_stop.pack(side="left", padx=2, ipadx=12)
        ttk.Button(btn, text="🧹 Clear output",
                   command=self._clear_output).pack(side="right", padx=2)

        self.run_status = tk.StringVar(value="Ready.")
        ttk.Label(panel, textvariable=self.run_status,
                  style="Sub.TLabel").grid(row=2, column=0, columnspan=5,
                                           sticky="w", pady=(6, 0))
        panel.columnconfigure(3, weight=1)

        ttk.Label(f, text="📤 Output:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.output = scrolledtext.ScrolledText(
            f, wrap="word", font=("Consolas", 10),
            bg="#0f1115", fg="#d0d0d0", insertbackground="white")
        self.output.pack(fill="both", expand=True, pady=(4, 0))
        self.output.tag_config("ok", foreground="#7ddc7d")
        self.output.tag_config("err", foreground="#ff6b6b")
        self.output.tag_config("info", foreground="#64b5f6")
        self.output.tag_config("sys", foreground="#ffc107",
                               font=("Consolas", 10, "bold"))

        stdin = ttk.Frame(f)
        stdin.pack(fill="x", pady=(6, 0))
        ttk.Label(stdin, text="⌨ Input:").pack(side="left")
        self.stdin_var = tk.StringVar()
        self.ent_stdin = ttk.Entry(stdin, textvariable=self.stdin_var)
        self.ent_stdin.pack(side="left", fill="x", expand=True, padx=6)
        self.ent_stdin.bind("<Return>", lambda e: self._send_stdin())
        ttk.Button(stdin, text="Send", command=self._send_stdin).pack(side="left")

        self._refresh_run_envs()

    def _refresh_run_envs(self):
        envs = [p.name for p in find_envs(self._work_path())]
        self.cb_run_env["values"] = envs
        if envs and not self.run_env.get():
            self.run_env.set(envs[0])

    def _run_pick_file(self):
        path = filedialog.askopenfilename(
            initialdir=self.work_dir.get(),
            filetypes=[("Python", "*.py"), ("All files", "*.*")])
        if path:
            self.run_file.set(path)

    def _run_start_clicked(self):
        name = self.run_env.get().strip()
        file = self.run_file.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Select an environment.")
            return
        if not file:
            messagebox.showwarning("Warning", "Select a Python script.")
            return
        self._run_start(name, Path(file))

    def _output_write(self, text, tag=None):
        self.output.insert("end", text, tag)
        self.output.see("end")

    def _clear_output(self):
        self.output.delete("1.0", "end")

    def _run_start(self, name, script: Path):
        if self.running_proc and self.running_proc.poll() is None:
            messagebox.showinfo("Already Running", "Stop the current process first.")
            return

        env_path = self._work_path() / name
        if not is_valid_env(env_path):
            messagebox.showerror("Error", f"'{name}' is not a valid environment.")
            return
        if not script.exists():
            messagebox.showerror("Error", f"Script not found: {script}")
            return

        self._clear_output()
        self._output_write(f"▶ Running: {script.name}\n", "sys")
        self._output_write(f"   Env    : {name}\n", "sys")
        self._output_write(f"   Python : {python_version(env_path)}\n", "sys")
        self._output_write("─" * 55 + "\n", "sys")

        self.run_status.set(f"Running: {script.name}")
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._busy_start(f"Running: {script.name}")

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            self.running_proc = subprocess.Popen(
                [str(python_exe(env_path)), "-u", str(script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                env=env,
                cwd=str(script.parent),
            )
        except Exception as e:
            self._output_write(f"❌ Failed to start: {e}\n", "err")
            self.run_status.set("Error.")
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            self._busy_end("Error.")
            return

        threading.Thread(target=self._read_output, daemon=True).start()
        threading.Thread(target=self._wait_for_exit, daemon=True).start()

    def _read_output(self):
        proc = self.running_proc
        if not proc or not proc.stdout:
            return
        try:
            for line in iter(proc.stdout.readline, ""):
                if line == "":
                    break
                self.root.after(0, lambda s=line: self._output_write(s))
        except Exception:
            pass

    def _wait_for_exit(self):
        proc = self.running_proc
        if not proc:
            return
        code = proc.wait()
        self.root.after(0, lambda: self._output_write(
            f"\n─{'─' * 54}\n", "sys"))
        if code == 0:
            self.root.after(0, lambda: self._output_write(
                f"✅ Process finished (exit code: {code})\n", "ok"))
        else:
            self.root.after(0, lambda: self._output_write(
                f"❌ Process exited with error (exit code: {code})\n", "err"))
        self.root.after(0, self._run_reset)

    def _run_reset(self):
        self.running_proc = None
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.run_status.set("Ready.")
        self._busy_end("Ready.")

    def _run_stop_clicked(self):
        if not self.running_proc:
            return
        if self.running_proc.poll() is not None:
            self._run_reset()
            return
        self._output_write("\n⏹ Stopping...\n", "sys")
        try:
            if WINDOWS:
                subprocess.run(["taskkill", "/F", "/T", "/PID",
                                str(self.running_proc.pid)],
                               capture_output=True)
            else:
                self.running_proc.terminate()
                try:
                    self.running_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.running_proc.kill()
            self._output_write("⏹ Process stopped.\n", "err")
        except Exception as e:
            self._output_write(f"⚠️  Could not stop: {e}\n", "err")
        self._run_reset()

    def _send_stdin(self):
        if not self.running_proc or self.running_proc.poll() is not None:
            return
        text = self.stdin_var.get()
        try:
            self.running_proc.stdin.write(text + "\n")
            self.running_proc.stdin.flush()
            self._output_write(f">>> {text}\n", "info")
        except Exception as e:
            self._output_write(f"⚠️  Could not send input: {e}\n", "err")
        self.stdin_var.set("")

    # =====================================================
    #  TAB: INFO
    # =====================================================
    def _build_tab_info(self):
        f = self.tab_info
        ttk.Label(f, text="🔍 Environment Info",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        ttk.Label(top, text="Environment:").pack(side="left")
        self.info_env = tk.StringVar(value="")
        self.cb_info = ttk.Combobox(top, textvariable=self.info_env, width=30)
        self.cb_info.pack(side="left", padx=6)
        ttk.Button(top, text="🔄 Refresh",
                   command=self._refresh_info_combo).pack(side="left", padx=4)
        ttk.Button(top, text="ℹ️ Show", style="Blue.TButton",
                   command=self._show_info).pack(side="left")
        ttk.Button(top, text="📋 Copy Activate Cmd",
                   command=self._copy_activate).pack(side="left", padx=4)

        self.info_text = scrolledtext.ScrolledText(
            f, wrap="word", font=("Consolas", 10),
            bg="#1e1e1e", fg="#e0e0e0", insertbackground="white")
        self.info_text.pack(fill="both", expand=True, pady=8)
        self._refresh_info_combo()

    # =====================================================
    #  TAB: LOG
    # =====================================================
    def _build_tab_log(self):
        f = self.tab_log
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="📜 Operation Log",
                  font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(top, text="🧹 Clear",
                   command=self._clear_log).pack(side="right")
        ttk.Button(top, text="💾 Save",
                   command=self._save_log).pack(side="right", padx=6)

        self.log_text = scrolledtext.ScrolledText(
            f, wrap="word", font=("Consolas", 10),
            bg="#111418", fg="#d0d0d0", insertbackground="white")
        self.log_text.pack(fill="both", expand=True, pady=8)
        self.log_text.tag_config("ok", foreground="#7ddc7d")
        self.log_text.tag_config("err", foreground="#ff6b6b")
        self.log_text.tag_config("warn", foreground="#ffc107")
        self.log_text.tag_config("info", foreground="#64b5f6")
        self.log_text.tag_config("hl", foreground="#ffffff",
                                 font=("Consolas", 10, "bold"))

    # =====================================================
    #  TAB: HELP
    # =====================================================
    def _build_tab_help(self):
        f = self.tab_help
        left = ttk.Frame(f)
        left.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(left, text="🎓 Topics",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        topics = [
            ("1. What is a virtual environment?", self.topic_what),
            ("2. What's inside the folder?", self.topic_contents),
            ("3. Basic commands", self.topic_basic),
            ("4. pip commands", self.topic_pip),
            ("5. requirements.txt", self.topic_req),
            ("6. Common errors", self.topic_errors),
            ("7. venv vs alternatives", self.topic_compare),
            ("8. Git usage", self.topic_git),
        ]
        for title, cmd in topics:
            ttk.Button(left, text=title, width=42, command=cmd).pack(fill="x", pady=3)

        self.help_text = scrolledtext.ScrolledText(
            f, wrap="word", font=("Consolas", 10),
            bg="#fbfcfe", fg="#222")
        self.help_text.pack(side="right", fill="both", expand=True)
        self.help_text.tag_config("title", foreground="#0d6efd",
                                  font=("Segoe UI", 12, "bold"))
        self.help_text.tag_config("sub", foreground="#198754",
                                  font=("Consolas", 10, "bold"))
        self.help_text.tag_config("code", foreground="#c7254e",
                                  background="#f9f2f4",
                                  font=("Consolas", 10))
        self.help_text.tag_config("warn", foreground="#b8860b",
                                  font=("Consolas", 10, "bold"))
        self.help_text.tag_config("gray", foreground="#777")

        self.topic_what()

    def _w(self, text, tag=None):
        self.help_text.insert("end", text, tag)

    def _clear_help(self):
        self.help_text.delete("1.0", "end")

    def topic_what(self):
        self._clear_help()
        self._w("📘 WHAT IS A VIRTUAL ENVIRONMENT?\n\n", "title")
        self._w("Definition:\n", "sub")
        self._w("  A virtual environment is an isolated Python installation\n"
                "  for your project. It has its own pip, its own packages,\n"
                "  and its own executable files.\n\n")
        self._w("Why use it?\n", "sub")
        self._w("  • Prevents dependency conflicts.\n"
                "    Project A needs Django 3, project B needs Django 5.\n"
                "    With virtual environments, both work side by side.\n\n"
                "  • Keeps the system Python clean.\n"
                "    Global 'pip install' commands can break system packages.\n\n"
                "  • Makes the project portable.\n"
                "    A requirements.txt recreates the same environment anywhere.\n\n"
                "  • Clean removal.\n"
                "    Just delete the folder — no traces left in the system.\n\n")
        self._w("💡 Example:\n", "warn")
        self._w("  python -m venv .venv\n"
                "  source .venv/bin/activate   # Linux/macOS\n"
                "  .venv\\Scripts\\activate      # Windows\n", "code")

    def topic_contents(self):
        self._clear_help()
        self._w("📁 WHAT'S INSIDE A VENV FOLDER?\n\n", "title")
        self._w("myenv/\n"
                "├── bin/                (Windows: Scripts/)\n"
                "│   ├── python          → environment's Python interpreter\n"
                "│   ├── python3         → symlink (Linux/macOS)\n"
                "│   ├── pip             → environment's pip\n"
                "│   ├── activate        → bash/zsh activation script\n"
                "│   ├── activate.csh    → for csh\n"
                "│   ├── activate.fish   → for fish\n"
                "│   └── Activate.ps1    → PowerShell activation script\n"
                "│\n"
                "├── include/            → C header files\n"
                "├── lib/\n"
                "│   └── python3.x/\n"
                "│       └── site-packages/  → ALL INSTALLED PACKAGES HERE\n"
                "│\n"
                "├── lib64/              → (some systems) 64-bit symlink\n"
                "└── pyvenv.cfg          → configuration file\n\n", "code")
        self._w("pyvenv.cfg example:\n", "sub")
        self._w("  home = /usr/bin\n"
                "  include-system-site-packages = false\n"
                "  version = 3.11.4\n\n", "code")
        self._w("⚠️ venv does NOT reinstall Python. It creates a symlink\n"
                "   (Windows: a copy) to the system Python plus an isolated\n"
                "   'site-packages' folder.\n", "warn")

    def topic_basic(self):
        self._clear_help()
        self._w("⌨️  BASIC COMMANDS\n\n", "title")
        self._w("■ CREATE\n", "sub")
        self._w("  python -m venv myenv\n"
                "  python -m venv myenv --system-site-packages\n"
                "  python3.11 -m venv myenv\n\n", "code")
        self._w("■ ACTIVATE\n", "sub")
        self._w("  Linux / macOS :  source myenv/bin/activate\n"
                "  Windows CMD   :  myenv\\Scripts\\activate\n"
                "  PowerShell    :  myenv\\Scripts\\Activate.ps1\n\n", "code")
        self._w("⚠️ PowerShell users may need:\n"
                "   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned\n\n", "warn")
        self._w("■ DEACTIVATE\n", "sub")
        self._w("  deactivate\n\n", "code")
        self._w("■ DELETE\n", "sub")
        self._w("  Linux/macOS :  rm -rf myenv\n"
                "  Windows     :  rmdir /s /q myenv\n\n", "code")
        self._w("■ AM I ACTIVE?\n", "sub")
        self._w("  Bash/Zsh :  echo $VIRTUAL_ENV\n"
                "  CMD      :  echo %VIRTUAL_ENV%\n"
                "  PowerShell: $env:VIRTUAL_ENV\n", "code")

    def topic_pip(self):
        self._clear_help()
        self._w("📦 PIP COMMANDS\n\n", "title")
        self._w("■ Install\n", "sub")
        self._w("  pip install requests\n"
                "  pip install requests==2.31.0\n"
                "  pip install \"requests>=2.30,<3\"\n"
                "  pip install -r requirements.txt\n"
                "  pip install -e .\n\n", "code")
        self._w("■ Uninstall\n", "sub")
        self._w("  pip uninstall requests\n\n", "code")
        self._w("■ List\n", "sub")
        self._w("  pip list\n"
                "  pip list --outdated\n"
                "  pip show requests\n\n", "code")
        self._w("■ Freeze\n", "sub")
        self._w("  pip freeze\n"
                "  pip freeze > requirements.txt\n\n", "code")
        self._w("■ Upgrade\n", "sub")
        self._w("  pip install --upgrade pip\n"
                "  pip install --upgrade requests\n"
                "  pip install --upgrade -r requirements.txt\n\n", "code")
        self._w("💡 Using 'python -m pip' is safer.\n", "warn")

    def topic_req(self):
        self._clear_help()
        self._w("📄 REQUIREMENTS.TXT\n\n", "title")
        self._w("Example contents:\n", "sub")
        self._w("  requests==2.31.0\n"
                "  flask>=2.3,<3.0\n"
                "  numpy\n"
                "  pandas==2.1.4\n"
                "  python-dotenv==1.0.0\n\n", "code")
        self._w("Generate:\n", "sub")
        self._w("  pip freeze > requirements.txt\n\n", "code")
        self._w("Install:\n", "sub")
        self._w("  pip install -r requirements.txt\n\n", "code")
        self._w("Advanced: split files\n", "sub")
        self._w("  requirements.txt       → production\n"
                "  requirements-dev.txt   → development (pytest, black)\n"
                "  requirements-test.txt  → testing\n\n", "code")
        self._w("💡 'pip freeze' lists all transitive deps. For direct ones only:\n"
                "     pip install pipreqs\n"
                "     pipreqs . --force\n", "warn")

    def topic_errors(self):
        self._clear_help()
        self._w("🐞 COMMON ERRORS\n\n", "title")
        errors = [
            ("1) pip: command not found",
             "Environment not activated. Run the activation command."),
            ("2) ModuleNotFoundError",
             "Wrong Python or package not installed. Check 'which python'."),
            ("3) PowerShell: Activate.ps1 cannot be loaded",
             "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned"),
            ("4) python -m venv fails (Linux)",
             "sudo apt install python3-venv"),
            ("5) Installed globally with system pip",
             "Always install inside an active environment."),
            ("6) Environment broken",
             "rm -rf myenv && python -m venv myenv"),
            ("7) Python version mismatch",
             "Environments are tied to a specific Python version."),
            ("8) Package conflicts across projects",
             "Each project should use its own environment."),
        ]
        for t, fix in errors:
            self._w(t + "\n", "warn")
            self._w("   → " + fix + "\n\n")

    def topic_compare(self):
        self._clear_help()
        self._w("⚖️  VENV vs VIRTUALENV vs CONDA vs POETRY\n\n", "title")
        self._w("┌────────────────┬──────────┬──────────────┬──────────┬─────────┐\n"
                "│ Tool           │ Standard │ Speed        │ Pip Fit  │ Lock    │\n"
                "├────────────────┼──────────┼──────────────┼──────────┼─────────┤\n"
                "│ venv           │   ✅     │   Fast       │   ✅     │  ❌     │\n"
                "│ virtualenv     │   ❌     │   Very fast  │   ✅     │  ❌     │\n"
                "│ conda          │   ❌     │   Slow       │   ⚠️     │  ✅     │\n"
                "│ poetry         │   ❌     │   Medium     │   ✅     │  ✅     │\n"
                "└────────────────┴──────────┴──────────────┴──────────┴─────────┘\n\n", "code")
        self._w("venv", "sub")
        self._w("  Standard since Python 3.3. Lightest and fastest.\n\n")
        self._w("virtualenv", "sub")
        self._w("  Predecessor of venv. Still used for Python 2 support.\n\n")
        self._w("conda", "sub")
        self._w("  Manages R and C libraries too. Popular in data science.\n\n")
        self._w("poetry", "sub")
        self._w("  Modern package manager. pyproject.toml + poetry.lock.\n\n")
        self._w("💡 Simple → venv | Complex → poetry | Data → conda\n", "warn")

    def topic_git(self):
        self._clear_help()
        self._w("🔀 GIT USAGE\n\n", "title")
        self._w("⚠️ NEVER commit the virtual environment folder to Git.\n\n", "warn")
        self._w(".gitignore example:\n", "sub")
        self._w("  venv/\n"
                "  .venv/\n"
                "  env/\n"
                "  ENV/\n"
                "  myenv/\n"
                "  __pycache__/\n"
                "  *.py[cod]\n"
                "  *.egg-info/\n"
                "  .pytest_cache/\n"
                "  .mypy_cache/\n"
                "  .vscode/\n"
                "  .idea/\n\n", "code")
        self._w("Team workflow:\n", "sub")
        self._w("  A: python -m venv .venv && source .venv/bin/activate\n"
                "     pip install requests flask\n"
                "     pip freeze > requirements.txt\n"
                "     git add requirements.txt && git commit -m \"deps\"\n\n"
                "  B: git clone <repo> && cd <repo>\n"
                "     python -m venv .venv && source .venv/bin/activate\n"
                "     pip install -r requirements.txt\n", "code")
        self._w("💡 '.venv' is a convention; VS Code and PyCharm auto-detect it.\n", "warn")

    # =====================================================
    #  HELPERS
    # =====================================================
    def _log(self, msg, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n", tag)
        self.log_text.see("end")

    def _clear_log(self):
        self.log_text.delete("1.0", "end")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log file", "*.log"), ("Text", "*.txt")])
        if path:
            Path(path).write_text(self.log_text.get("1.0", "end"), encoding="utf-8")
            messagebox.showinfo("Saved", f"Log saved to:\n{path}")

    def _pick_dir(self):
        path = filedialog.askdirectory(initialdir=self.work_dir.get())
        if path:
            self.work_dir.set(path)
            self._refresh_all()

    def _pick_req(self):
        path = filedialog.askopenfilename(
            initialdir=self.work_dir.get(),
            filetypes=[("requirements", "requirements*.txt"), ("All", "*.*")])
        if path:
            self.req_file.set(path)

    def _refresh_all(self):
        self._refresh_envs()
        self._refresh_info_combo()
        self._refresh_run_envs()

    def _work_path(self):
        return Path(self.work_dir.get()).expanduser().resolve()

    def _busy_start(self, msg="Working..."):
        self.busy = True
        self.status.set(msg)
        self.progress.start(10)

    def _busy_end(self, msg="Ready."):
        self.busy = False
        self.status.set(msg)
        self.progress.stop()

    # =====================================================
    #  CREATE ENV
    # =====================================================
    def _create_env_clicked(self):
        if self.busy:
            messagebox.showwarning("Please wait", "A task is already running.")
            return
        name = self.env_name.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Environment name cannot be empty.")
            return
        pkgs = self.packages.get().split()
        req = self.req_file.get().strip() or None

        self._busy_start(f"Creating '{name}'...")
        self.notebook.select(self.tab_log)

        threading.Thread(
            target=self._create_env_worker,
            args=(name, pkgs, req,
                  self.opt_system_site.get(),
                  self.opt_upgrade_pip.get(),
                  self.opt_symlink.get(),
                  self.opt_clear.get()),
            daemon=True,
        ).start()

    def _create_env_worker(self, name, pkgs, req, system_site,
                           upgrade_pip, symlink, clear):
        env_path = self._work_path() / name
        self._log("=" * 55, "hl")
        self._log(f"🚀 Creating: {env_path}", "hl")

        if env_path.exists():
            if clear:
                self._log(f"🗑️  Deleting '{name}'...", "warn")
                try:
                    shutil.rmtree(env_path)
                except Exception as e:
                    self._log(f"❌ Could not delete: {e}", "err")
                    self.root.after(0, lambda: self._busy_end("Error."))
                    return
            elif is_valid_env(env_path):
                self._log(f"⚠️  '{name}' is already a virtual environment.", "warn")
                self.root.after(0, lambda: self._busy_end("Existing."))
                return
            else:
                self._log(f"❌ '{name}' folder exists and is not empty.", "err")
                self.root.after(0, lambda: self._busy_end("Error."))
                return

        self._log("📦 Running venv module...", "info")
        try:
            builder = venv.EnvBuilder(
                system_site_packages=system_site, clear=False,
                symlinks=symlink, with_pip=True, upgrade_deps=False)
            builder.create(env_path)
        except Exception as e:
            self._log(f"❌ Could not create: {e}", "err")
            self.root.after(0, lambda: self._busy_end("Error."))
            return

        self._log(f"✅ Environment ready: {env_path}", "ok")

        if upgrade_pip:
            self._log("🔄 Upgrading pip...", "info")
            try:
                subprocess.run(
                    [str(python_exe(env_path)), "-m", "pip", "install", "--upgrade", "pip"],
                    check=True, capture_output=True, text=True)
                self._log("✅ pip upgraded.", "ok")
            except subprocess.CalledProcessError as e:
                self._log(f"⚠️  Could not upgrade pip: {e.stderr.strip()}", "warn")

        if req and Path(req).exists():
            self._log(f"📄 requirements.txt: {req}", "info")
            self._run_pip(env_path, ["install", "-r", req], "requirements.txt")

        if pkgs:
            self._log(f"📦 Packages: {', '.join(pkgs)}", "info")
            self._run_pip(env_path, ["install", *pkgs], "packages")

        self._log(f"🐍 Python   : {python_version(env_path)}", "ok")
        self._log(f"💾 Size     : {folder_size(env_path)}", "ok")
        self._log(f"🔧 Activate : {activate_cmd(name)}", "ok")
        self._log("=" * 55, "hl")

        self.root.after(0, self._refresh_all)
        self.root.after(0, lambda: self._busy_end(f"Ready: {name}"))
        self.root.after(0, lambda: messagebox.showinfo(
            "Environment Ready",
            f"'{name}' is ready!\n\nActivate:\n  {activate_cmd(name)}\n\n"
            f"Deactivate:\n  deactivate"))

    def _run_pip(self, env_path, args, label):
        try:
            r = subprocess.run(
                [str(python_exe(env_path)), "-m", "pip", *args],
                capture_output=True, text=True)
            if r.returncode == 0:
                self._log(f"✅ {label} done.", "ok")
            else:
                self._log(f"⚠️  {label}:\n{r.stderr}", "warn")
        except Exception as e:
            self._log(f"❌ {label}: {e}", "err")

    # =====================================================
    #  ENV LIST / DELETE
    # =====================================================
    def _refresh_envs(self):
        self.tree.delete(*self.tree.get_children())
        envs = find_envs(self._work_path())
        for env in sorted(envs, key=lambda p: p.name.lower()):
            created = datetime.fromtimestamp(env.stat().st_ctime).strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", values=(
                env.name, python_version(env), folder_size(env),
                created, str(env)))
        if hasattr(self, "status"):
            self.status.set(f"{len(envs)} environment(s) found.")

    def _envs_update_selection(self):
        sel = self.tree.selection()
        if sel:
            v = self.tree.item(sel[0], "values")
            self.sel_info.set(f"Selected: {v[0]} | Python {v[1]} | {v[2]} | {v[4]}")

    def _envs_delete_selected(self):
        if self.busy:
            messagebox.showwarning("Please wait", "A task is running.")
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select an environment to delete.")
            return
        name = self.tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm",
                                   f"Delete '{name}'?\n\nThis cannot be undone."):
            return
        path = self._work_path() / name
        try:
            shutil.rmtree(path)
            self._log(f"🗑️  Deleted: {path}", "warn")
            self._refresh_all()
        except Exception as e:
            messagebox.showerror("Error", f"Could not delete: {e}")
            self._log(f"❌ Could not delete: {e}", "err")

    def _envs_show_info(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0], "values")[0]
        self.info_env.set(name)
        self.notebook.select(self.tab_info)
        self._show_info()

    # =====================================================
    #  INFO TAB
    # =====================================================
    def _refresh_info_combo(self):
        envs = [p.name for p in find_envs(self._work_path())]
        self.cb_info["values"] = envs
        if envs and not self.info_env.get():
            self.info_env.set(envs[0])

    def _show_info(self):
        name = self.info_env.get().strip()
        if not name:
            messagebox.showinfo("Info", "Select an environment.")
            return
        path = self._work_path() / name
        if not is_valid_env(path):
            messagebox.showerror("Error", f"'{name}' is not a valid environment.")
            return

        self.info_text.delete("1.0", "end")
        b = self.info_text
        b.tag_config("title", foreground="#4fc3f7",
                     font=("Consolas", 12, "bold"))
        b.tag_config("label", foreground="#ffd54f")
        b.tag_config("value", foreground="#a5d6a7")
        b.tag_config("gray", foreground="#888")

        b.insert("end", f"🔍 {name}\n", "title")
        b.insert("end", "─" * 55 + "\n", "gray")

        rows = [
            ("📁 Path", str(path)),
            ("🐍 Python", python_version(path)),
            ("💾 Size", folder_size(path)),
            ("📅 Created",
             datetime.fromtimestamp(path.stat().st_ctime).strftime("%Y-%m-%d %H:%M")),
            ("🔧 Activate", activate_cmd(name)),
            ("❌ Deactivate", "deactivate"),
        ]
        for k, v in rows:
            b.insert("end", f"{k:<18}: ", "label")
            b.insert("end", f"{v}\n", "value")

        b.insert("end", "\n📦 Installed Packages\n", "title")
        b.insert("end", "─" * 55 + "\n", "gray")
        try:
            r = subprocess.run(
                [str(python_exe(path)), "-m", "pip", "list", "--format=freeze"],
                capture_output=True, text=True)
            for line in r.stdout.strip().splitlines()[:50]:
                b.insert("end", f"  {line}\n", "value")
        except Exception as e:
            b.insert("end", f"  (could not read: {e})\n", "gray")

    def _copy_activate(self):
        name = self.info_env.get().strip()
        if not name:
            return
        cmd = activate_cmd(name)
        self.root.clipboard_clear()
        self.root.clipboard_append(cmd)
        messagebox.showinfo("Copied", f"Copied to clipboard:\n{cmd}")


# =========================================================
#  ENTRY POINT
# =========================================================
def main():
    root = tk.Tk()
    try:
        if WINDOWS:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    VenvManagerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
