from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from transformer_client.backend import BackendError, UnauthorizedError
from transformer_client.control import MotorControlError
from transformer_client.controller import LiveClientController
from transformer_client.state import UiRow


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
        self.motor_status_var = tk.StringVar(value="Motor: IDLE | STOPPED")
        self.motor_message_var = tk.StringVar(value="Brak aktywnego rejestru.")
        self.selected_register_var = tk.StringVar(value="Brak zaznaczenia")
        self.current_value_var = tk.StringVar(value="-")
        self.control_target_var = tk.StringVar(value="")
        self.control_threshold_var = tk.StringVar(value="")
        self.activate_control_var = tk.BooleanVar(value=False)

        self._tree: ttk.Treeview | None = None
        self._target_entry: ttk.Entry | None = None
        self._threshold_entry: ttk.Entry | None = None
        self._login_button: ttk.Button | None = None
        self._main_frame: ttk.Frame | None = None
        self._rows_by_key: dict[str, UiRow] = {}
        self._selected_key: str | None = None
        self._refreshing_tree = False

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
        frame.rowconfigure(4, weight=1)
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

        ttk.Label(frame, textvariable=self.summary_var).grid(row=1, column=0, sticky="w", pady=(0, 4))
        ttk.Label(frame, textvariable=self.backend_error_var, foreground="#b42318").grid(
            row=1,
            column=0,
            sticky="e",
            pady=(0, 4),
        )
        ttk.Label(frame, textvariable=self.motor_status_var).grid(row=2, column=0, sticky="w", pady=(0, 4))
        ttk.Label(frame, textvariable=self.motor_message_var, foreground="#444").grid(
            row=2,
            column=0,
            sticky="e",
            pady=(0, 4),
        )

        control_frame = ttk.LabelFrame(frame, text="Sterowanie", padding=12)
        control_frame.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        control_frame.columnconfigure(1, weight=1)
        control_frame.columnconfigure(3, weight=1)

        ttk.Label(control_frame, text="Wybrany rejestr").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(control_frame, textvariable=self.selected_register_var).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(control_frame, text="Aktualna wartosc").grid(row=0, column=2, sticky="w", pady=4)
        ttk.Label(control_frame, textvariable=self.current_value_var).grid(row=0, column=3, sticky="w", pady=4)

        ttk.Label(control_frame, text="Target").grid(row=1, column=0, sticky="w", pady=4)
        self._target_entry = ttk.Entry(control_frame, textvariable=self.control_target_var, width=18)
        self._target_entry.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(control_frame, text="Threshold").grid(row=1, column=2, sticky="w", pady=4)
        self._threshold_entry = ttk.Entry(control_frame, textvariable=self.control_threshold_var, width=18)
        self._threshold_entry.grid(row=1, column=3, sticky="w", pady=4)
        ttk.Checkbutton(
            control_frame,
            text="Aktywuj sterowanie dla tego rejestru",
            variable=self.activate_control_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Button(control_frame, text="Apply", command=self._apply_control).grid(row=2, column=2, sticky="e", padx=6)
        ttk.Button(control_frame, text="Stop control", command=self._clear_active_control).grid(row=2, column=3, sticky="w")

        columns = ("meter", "port", "status", "register", "value", "target", "threshold", "active", "unit", "updated", "address", "type")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        headings = {
            "meter": "Meter",
            "port": "Port",
            "status": "Status",
            "register": "Register",
            "value": "Value",
            "target": "Target",
            "threshold": "Threshold",
            "active": "Control",
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
            "target": 100,
            "threshold": 100,
            "active": 90,
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
        tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        tree.grid(row=4, column=0, sticky="nsew")
        scrollbar.grid(row=4, column=1, sticky="ns")
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
        self.motor_status_var.set(f"Motor: {snapshot['motor_state']} | {snapshot['motor_direction']}")
        self.motor_message_var.set(snapshot["motor_message"])

        self._rows_by_key = {}
        self._refreshing_tree = True
        try:
            existing_ids = set(self._tree.get_children())
            next_ids: set[str] = set()
            for row in snapshot["rows"]:
                item_id = f"{row.meter_id}:{row.register_id}"
                next_ids.add(item_id)
                self._rows_by_key[item_id] = row
                values = (
                    row.meter_name,
                    row.serial_port,
                    row.status,
                    row.register_name,
                    format_value(row.value),
                    format_value(row.target_value),
                    format_value(row.threshold_value),
                    "ACTIVE" if row.control_active else "-",
                    row.unit or "",
                    format_timestamp(row.updated_at),
                    row.address,
                    row.data_type,
                )
                if item_id in existing_ids:
                    self._tree.item(item_id, values=values)
                else:
                    self._tree.insert("", "end", iid=item_id, values=values)

            for item_id in existing_ids - next_ids:
                self._tree.delete(item_id)

            if self._selected_key and self._selected_key in self._rows_by_key:
                self._tree.selection_set(self._selected_key)
                self._sync_selected_row(self._rows_by_key[self._selected_key], preserve_inputs=True)
            elif self._selected_key and self._selected_key not in self._rows_by_key:
                self._selected_key = None
                self.selected_register_var.set("Brak zaznaczenia")
                self.current_value_var.set("-")
        finally:
            self._refreshing_tree = False

    def _on_tree_select(self, _event) -> None:
        if self._refreshing_tree:
            return
        if self._tree is None:
            return
        selection = self._tree.selection()
        if not selection:
            return
        self._selected_key = selection[0]
        row = self._rows_by_key.get(self._selected_key)
        if row is not None:
            self._sync_selected_row(row, preserve_inputs=False)

    def _sync_selected_row(self, row: UiRow, preserve_inputs: bool) -> None:
        self.selected_register_var.set(f"{row.meter_name} / {row.register_name} ({row.register_id})")
        self.current_value_var.set(format_value(row.value))
        if not preserve_inputs or not self._editing_control_inputs():
            self.control_target_var.set("" if row.target_value is None else str(row.target_value))
            self.control_threshold_var.set("" if row.threshold_value is None else str(row.threshold_value))
            self.activate_control_var.set(row.control_active)

    def _apply_control(self) -> None:
        row = self._require_selected_row()
        if row is None:
            return
        try:
            target = parse_optional_float(self.control_target_var.get())
            threshold = parse_optional_float(self.control_threshold_var.get())
            self.controller.set_register_control(
                row.meter_id,
                row.register_id,
                target,
                threshold,
                self.activate_control_var.get(),
            )
        except (ValueError, MotorControlError, KeyError) as exc:
            messagebox.showerror("Sterowanie", str(exc))
            return
        self._refresh_ui()

    def _clear_active_control(self) -> None:
        self.controller.clear_active_register_control()
        self.activate_control_var.set(False)
        self._refresh_ui()

    def _require_selected_row(self) -> UiRow | None:
        if self._selected_key is None:
            messagebox.showerror("Sterowanie", "Najpierw wybierz rejestr z tabeli.")
            return None
        row = self._rows_by_key.get(self._selected_key)
        if row is None:
            messagebox.showerror("Sterowanie", "Wybrany rejestr nie jest juz dostepny.")
            return None
        return row

    def _editing_control_inputs(self) -> bool:
        focused = self.root.focus_get()
        return focused in {self._target_entry, self._threshold_entry}

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


def parse_optional_float(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    return float(stripped)
