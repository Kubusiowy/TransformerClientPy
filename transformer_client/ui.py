from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from transformer_client.backend import BackendError, UnauthorizedError
from transformer_client.controller import LiveClientController


class LiveClientApp:
    def __init__(self, controller: LiveClientController) -> None:
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("Transformer Client Live")
        self.root.geometry("1200x720")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.backend_url_var = tk.StringVar(value=self.controller.config.backendUrl)
        self.email_var = tk.StringVar(value=self.controller.config.email)
        self.password_var = tk.StringVar(value=self.controller.config.password)
        self.remember_var = tk.BooleanVar(value=self.controller.config.rememberCredentials)
        self.status_var = tk.StringVar(value="Login required.")
        self.backend_error_var = tk.StringVar(value="")
        self.transformer_var = tk.StringVar(value="-")
        self.summary_var = tk.StringVar(value="Meters: 0 | Registers: 0")

        self._tree: ttk.Treeview | None = None
        self._login_button: ttk.Button | None = None
        self._main_frame: ttk.Frame | None = None

        self._build_login_view()

    def run(self) -> None:
        self.root.mainloop()

    def _build_login_view(self) -> None:
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Backend URL").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.backend_url_var).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="Email").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.email_var).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="Haslo").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.password_var, show="*").grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(frame, text="Remember credentials", variable=self.remember_var).grid(
            row=3,
            column=1,
            sticky="w",
            pady=6,
        )

        self._login_button = ttk.Button(frame, text="Zaloguj", command=self._start_login)
        self._login_button.grid(row=4, column=1, sticky="e", pady=12)

        ttk.Label(frame, textvariable=self.status_var, foreground="#444").grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=8,
        )

    def _build_main_view(self) -> None:
        if self._main_frame is not None:
            self._main_frame.destroy()

        for child in self.root.winfo_children():
            child.destroy()

        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        self._main_frame = frame

        top_bar = ttk.Frame(frame)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_bar.columnconfigure(0, weight=1)

        ttk.Label(top_bar, textvariable=self.transformer_var, font=("TkDefaultFont", 12, "bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Button(top_bar, text="Refresh config", command=self._refresh_config_async).grid(row=0, column=1, padx=6)
        ttk.Button(top_bar, text="Wyloguj", command=self._logout).grid(row=0, column=2)

        ttk.Label(frame, textvariable=self.summary_var).grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Label(frame, textvariable=self.backend_error_var, foreground="#b42318").grid(
            row=1,
            column=0,
            sticky="e",
            pady=(0, 8),
        )

        columns = ("meter", "port", "status", "register", "value", "unit", "updated", "address", "type")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        headings = {
            "meter": "Meter",
            "port": "Port",
            "status": "Status",
            "register": "Register",
            "value": "Value",
            "unit": "Unit",
            "updated": "Last update",
            "address": "Address",
            "type": "Type",
        }
        widths = {
            "meter": 150,
            "port": 150,
            "status": 110,
            "register": 160,
            "value": 100,
            "unit": 70,
            "updated": 170,
            "address": 90,
            "type": 120,
        }
        for key in columns:
            tree.heading(key, text=headings[key])
            tree.column(key, width=widths[key], anchor="w")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        self._tree = tree

        self._schedule_ui_refresh()

    def _start_login(self) -> None:
        backend_url = self.backend_url_var.get().strip()
        email = self.email_var.get().strip()
        password = self.password_var.get()
        remember = self.remember_var.get()
        if not backend_url or not email or not password:
            messagebox.showerror("Brak danych", "Backend URL, email i haslo sa wymagane.")
            return

        self.status_var.set("Logowanie...")
        if self._login_button is not None:
            self._login_button.configure(state="disabled")

        def worker() -> None:
            try:
                self.controller.set_backend_url(backend_url)
                self.controller.login(email, password, remember)
            except (BackendError, UnauthorizedError) as exc:
                self.root.after(0, lambda: self._handle_login_error(str(exc)))
                return
            except Exception as exc:
                self.root.after(0, lambda: self._handle_login_error(f"Unexpected error: {exc}"))
                return
            self.root.after(0, self._handle_login_success)

        threading.Thread(target=worker, daemon=True, name="login").start()

    def _handle_login_success(self) -> None:
        self.status_var.set("Zalogowano.")
        self._build_main_view()

    def _handle_login_error(self, message: str) -> None:
        if self._login_button is not None:
            self._login_button.configure(state="normal")
        self.status_var.set(message)
        messagebox.showerror("Logowanie nieudane", message)

    def _schedule_ui_refresh(self) -> None:
        self._refresh_ui()
        self.root.after(300, self._schedule_ui_refresh)

    def _refresh_ui(self) -> None:
        if self._tree is None:
            return
        snapshot = self.controller.state.snapshot()
        selected = snapshot["selected_transformer"]
        if selected is None:
            self.transformer_var.set("Transformer: -")
        else:
            location = selected.location or "-"
            self.transformer_var.set(f"Transformer: {selected.name} | {selected.id} | {location}")

        self.summary_var.set(
            f"Meters: {snapshot['meter_count']} | Registers: {snapshot['register_count']}"
        )
        self.backend_error_var.set(snapshot["backend_error"] or "")

        self._tree.delete(*self._tree.get_children())
        for row in snapshot["rows"]:
            self._tree.insert(
                "",
                "end",
                values=(
                    row.meter_name,
                    row.serial_port,
                    row.status,
                    row.register_name,
                    format_value(row.value),
                    row.unit or "",
                    format_timestamp(row.updated_at),
                    row.address,
                    row.data_type,
                ),
            )

    def _refresh_config_async(self) -> None:
        self.backend_error_var.set("Refreshing configuration...")

        def worker() -> None:
            try:
                self.controller.refresh_configuration()
            except Exception as exc:
                self.root.after(0, lambda: self.backend_error_var.set(str(exc)))
                return
            self.root.after(0, lambda: self.backend_error_var.set(""))

        threading.Thread(target=worker, daemon=True, name="manual-refresh").start()

    def _logout(self) -> None:
        self.controller.shutdown()
        self.root.destroy()

    def _on_close(self) -> None:
        self.controller.shutdown()
        self.root.destroy()


def format_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M:%S")
