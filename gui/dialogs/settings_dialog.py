"""Settings dialog for paths, limits and logging."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gui import theme, utils
from gui.widgets import primary_button, secondary_button
from services.config import LOG_LEVELS, SEARCH_LIMITS, sync_folder_name

logger = logging.getLogger(__name__)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent)
        self.app = app
        self._old_token_path = app.settings.token_path
        self.title("Settings")
        self.configure(bg=theme.CARD)
        self.transient(parent.winfo_toplevel())
        self.geometry("700x780")
        self.minsize(620, 700)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _event: self._close())

        self._build()
        self._load()
        try:
            self.grab_set()
        except tk.TclError:  # pragma: no cover
            pass

    # -- layout ----------------------------------------------------------

    def _build(self) -> None:
        outer = tk.Frame(self, bg=theme.CARD, padx=24, pady=20)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="Settings", bg=theme.CARD, fg=theme.TEXT,
                 font=(theme.current().family, 15, "bold")).pack(anchor="w")
        tk.Label(
            outer,
            text=f"Configuration folder: {self.app.settings.config_folder}",
            bg=theme.CARD, fg=theme.MUTED, font=theme.current().small,
            wraplength=620, justify="left", anchor="w",
        ).pack(anchor="w", pady=(3, 16))

        # Database path ---------------------------------------------------
        tk.Label(outer, text="Database", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w")
        db_row = tk.Frame(outer, bg=theme.CARD)
        db_row.pack(fill="x", pady=(3, 4))
        self.db_var = tk.StringVar()
        self.db_entry = ttk.Entry(db_row, textvariable=self.db_var,
                                  font=theme.current().base)
        self.db_entry.pack(side="left", fill="x", expand=True)
        secondary_button(db_row, "Browse…", self._browse_db).pack(side="left", padx=(8, 0))
        self.db_hint = tk.Label(outer, text="", bg=theme.CARD, fg=theme.WARNING,
                                font=theme.current().tiny, anchor="w",
                                wraplength=620, justify="left")
        self.db_hint.pack(fill="x")

        # Token path ------------------------------------------------------
        tk.Label(outer, text="DigiKey token file", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w", pady=(10, 0))
        token_row = tk.Frame(outer, bg=theme.CARD)
        token_row.pack(fill="x", pady=(3, 4))
        self.token_var = tk.StringVar()
        self.token_entry = ttk.Entry(token_row, textvariable=self.token_var,
                                     font=theme.current().base)
        self.token_entry.pack(side="left", fill="x", expand=True)
        secondary_button(token_row, "Browse…", self._browse_token).pack(side="left", padx=(8, 0))

        self.token_status = tk.Label(outer, text="", bg=theme.CARD, fg=theme.MUTED,
                                     font=theme.current().small, anchor="w")
        self.token_status.pack(fill="x")

        # Limits ----------------------------------------------------------
        limits = tk.Frame(outer, bg=theme.CARD)
        limits.pack(fill="x", pady=(16, 0))
        limits.grid_columnconfigure(0, weight=1)
        limits.grid_columnconfigure(1, weight=1)

        left = tk.Frame(limits, bg=theme.CARD)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 18))
        tk.Label(left, text="Search result limit", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w")
        self.limit_var = tk.StringVar()
        self.limit_combo = ttk.Combobox(
            left, textvariable=self.limit_var, state="readonly",
            values=[str(value) for value in SEARCH_LIMITS], width=8,
            font=theme.current().base,
        )
        self.limit_combo.pack(anchor="w", pady=(3, 12))

        tk.Label(left, text="HTTP timeout (seconds)", bg=theme.CARD,
                 fg=theme.TEXT_SOFT, font=theme.current().small).pack(anchor="w")
        self.timeout_var = tk.StringVar()
        self.timeout_spin = tk.Spinbox(
            left, from_=5, to=300, increment=5, width=8, textvariable=self.timeout_var,
            font=theme.current().small, relief="flat", bg=theme.WHITE,
            highlightbackground=theme.BORDER_STRONG, highlightthickness=1,
        )
        self.timeout_spin.pack(anchor="w", pady=(3, 12))

        right = tk.Frame(limits, bg=theme.CARD)
        right.grid(row=0, column=1, sticky="nw")
        tk.Label(right, text="Batch request delay (ms)", bg=theme.CARD,
                 fg=theme.TEXT_SOFT, font=theme.current().small).pack(anchor="w")
        self.delay_var = tk.StringVar()
        self.delay_spin = tk.Spinbox(
            right, from_=0, to=10000, increment=50, width=8, textvariable=self.delay_var,
            font=theme.current().small, relief="flat", bg=theme.WHITE,
            highlightbackground=theme.BORDER_STRONG, highlightthickness=1,
        )
        self.delay_spin.pack(anchor="w", pady=(3, 12))

        tk.Label(right, text="Log level", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w")
        self.log_var = tk.StringVar()
        self.log_combo = ttk.Combobox(
            right, textvariable=self.log_var, state="readonly",
            values=list(LOG_LEVELS), width=10, font=theme.current().base,
        )
        self.log_combo.pack(anchor="w", pady=(3, 12))

        # Maintenance -----------------------------------------------------
        maintenance = tk.Frame(outer, bg=theme.CARD)
        maintenance.pack(fill="x", pady=(8, 0))
        secondary_button(maintenance, "Reveal config folder",
                         self._reveal_config).pack(side="left")
        self.clear_auth_button = secondary_button(
            maintenance, "Clear authentication", self._clear_auth
        )
        self.clear_auth_button.pack(side="left", padx=(8, 0))

        # Buttons ---------------------------------------------------------
        buttons = tk.Frame(outer, bg=theme.CARD)
        buttons.pack(fill="x", side="bottom", pady=(18, 0))
        secondary_button(buttons, "Cancel", self._close).pack(side="right")
        primary_button(buttons, "Save", self._save, padx=24).pack(side="right", padx=(0, 8))

    # -- data ------------------------------------------------------------

    def _load(self) -> None:
        settings = self.app.settings
        self.db_var.set(settings.database_path)
        self.token_var.set(settings.token_path)
        self.limit_var.set(str(settings.search_limit))
        self.timeout_var.set(str(settings.http_timeout))
        self.delay_var.set(str(settings.batch_delay_ms))
        self.log_var.set(settings.log_level)
        self._update_hints()
        self.db_var.trace_add("write", lambda *_args: self._update_hints())

    def _update_hints(self) -> None:
        sync = sync_folder_name(self.db_var.get()) if self.db_var.get() else None
        if sync:
            self.db_hint.configure(
                text=f"⚠ This path is inside {sync}. Sync clients can lock or corrupt "
                     "SQLite files; a local folder such as ~/KiCadLibGen is safer."
            )
        else:
            self.db_hint.configure(text="")
        status = self.app.auth.status()
        self.token_status.configure(text=f"Token: {status.summary}")

    # -- browse ----------------------------------------------------------

    def _browse_db(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Choose a components database",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if path:
            self.db_var.set(path)

    def _browse_token(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Choose a token file",
            filetypes=[("Token file", "*.token"), ("JSON", "*.json"),
                       ("All files", "*.*")],
        )
        if path:
            self.token_var.set(path)

    # -- actions ---------------------------------------------------------

    def _reveal_config(self) -> None:
        utils.reveal_folder(self.app.settings.config_folder)

    def _clear_auth(self) -> None:
        if not messagebox.askyesno(
            "Clear authentication?",
            "Remove the stored DigiKey token? You will need to sign in again.",
            parent=self,
        ):
            return
        try:
            self.app.auth.clear()
        except Exception as exc:
            messagebox.showerror("Could not clear token", str(exc), parent=self)
            return
        self.app.on_token_changed()
        self._update_hints()
        self.token_status.configure(text="Token: Not signed in")

    def _save(self) -> None:
        try:
            timeout = max(5, min(300, int(float(self.timeout_var.get()))))
            delay = max(0, min(10000, int(float(self.delay_var.get()))))
            limit = int(self.limit_var.get())
        except (TypeError, ValueError):
            messagebox.showerror("Invalid settings",
                                 "Search limit, timeout and delay must be numbers.",
                                 parent=self)
            return
        database = self.db_var.get().strip()
        token = self.token_var.get().strip()
        if not database or not token:
            messagebox.showerror("Invalid settings",
                                 "Database and token paths cannot be empty.",
                                 parent=self)
            return

        settings = self.app.settings
        settings.database_path = database
        settings.token_path = token
        settings.search_limit = limit
        settings.http_timeout = timeout
        settings.batch_delay_ms = delay
        settings.log_level = self.log_var.get()
        try:
            settings.save()
        except OSError as exc:
            messagebox.showerror("Could not save settings", str(exc), parent=self)
            return
        self.app.apply_settings(previous_token_path=self._old_token_path)
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
