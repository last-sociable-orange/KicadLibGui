"""DigiKey authentication dialog (three-step paste-the-callback flow)."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from gui import theme
from gui.widgets import primary_button, secondary_button
from kicad_core.errors import AppError, AuthError

logger = logging.getLogger(__name__)


class AuthDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, app, on_success: Callable[[dict[str, Any]], None] | None = None):
        super().__init__(parent)
        self.app = app
        self.on_success = on_success
        self._state: str | None = None
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._closed = False

        self.title("DigiKey authentication")
        self.configure(bg=theme.CARD)
        self.transient(parent.winfo_toplevel())
        self.geometry("640x790")
        self.minsize(560, 700)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _event: self._close())

        self._build()
        self._load_existing()
        self.after(10, self._focus_first)
        try:
            self.grab_set()
        except tk.TclError:  # pragma: no cover - non-modal in odd WMs
            pass

    # -- layout ----------------------------------------------------------

    def _build(self) -> None:
        outer = tk.Frame(self, bg=theme.CARD, padx=24, pady=20)
        outer.pack(fill="both", expand=True)

        heading = tk.Frame(outer, bg=theme.CARD)
        heading.pack(fill="x")
        tk.Label(
            heading, text="Connect your DigiKey account", bg=theme.CARD,
            fg=theme.TEXT, font=(theme.current().family, 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            heading,
            text="Use the Client ID and Client secret from your DigiKey developer app.",
            bg=theme.CARD, fg=theme.MUTED, font=theme.current().small,
        ).pack(anchor="w", pady=(3, 0))

        form = tk.Frame(outer, bg=theme.CARD)
        form.pack(fill="x", pady=(16, 0))

        tk.Label(form, text="Client ID", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w")
        self.client_id_var = tk.StringVar()
        self.client_id_entry = ttk.Entry(form, textvariable=self.client_id_var,
                                         font=theme.current().base)
        self.client_id_entry.pack(fill="x", pady=(3, 10))

        secret_row = tk.Frame(form, bg=theme.CARD)
        secret_row.pack(fill="x")
        tk.Label(secret_row, text="Client secret", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(side="left")
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            secret_row, text="Show", variable=self.show_var,
            command=self._toggle_secret, style="TCheckbutton",
        ).pack(side="right")
        self.secret_var = tk.StringVar()
        self.secret_entry = ttk.Entry(form, textvariable=self.secret_var, show="•",
                                      font=theme.current().base)
        self.secret_entry.pack(fill="x", pady=(3, 12))

        steps = tk.Frame(outer, bg=theme.ACCENT_SOFT, padx=14, pady=10)
        steps.pack(fill="x", pady=(4, 12))
        for number, text in (
            (1, "Open the DigiKey sign-in page."),
            (2, "Authorize this app for your account."),
            (3, "Copy the localhost URL from your browser and paste it below."),
        ):
            row = tk.Frame(steps, bg=theme.ACCENT_SOFT)
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=str(number), bg=theme.ACCENT, fg=theme.WHITE,
                font=(theme.current().family, 8, "bold"), width=2, height=1,
            ).pack(side="left", padx=(0, 8))
            tk.Label(
                row, text=text, bg=theme.ACCENT_SOFT, fg=theme.TEXT_SOFT,
                font=theme.current().small, anchor="w", justify="left",
                wraplength=460,
            ).pack(side="left", fill="x", expand=True)

        signin_row = tk.Frame(outer, bg=theme.CARD)
        signin_row.pack(fill="x", pady=(0, 10))
        self.signin_button = secondary_button(
            signin_row, "Open DigiKey sign-in page", self._open_sign_in
        )
        self.signin_button.pack(side="left", fill="x", expand=True)
        self.copy_button = secondary_button(signin_row, "Copy link", self._copy_sign_in)
        self.copy_button.pack(side="left", padx=(8, 0))

        tk.Label(outer, text="Redirect URL", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w")
        self.redirect_var = tk.StringVar()
        self.redirect_entry = ttk.Entry(outer, textvariable=self.redirect_var,
                                        font=theme.current().base)
        self.redirect_entry.pack(fill="x", pady=(3, 4))
        tk.Label(
            outer,
            text="Your browser will show a connection error at localhost - that is expected. "
                 "Copy the full URL from its address bar.",
            bg=theme.CARD, fg=theme.MUTED, font=theme.current().tiny,
            wraplength=560, justify="left",
        ).pack(anchor="w")

        self.status_row = tk.Frame(outer, bg=theme.CARD)
        self.status_row.pack(fill="x", pady=(12, 0))
        self.status_dot = tk.Label(self.status_row, text="●", bg=theme.CARD,
                                   fg=theme.FAINT, font=theme.current().small)
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(
            self.status_row, text="Not signed in", bg=theme.CARD, fg=theme.MUTED,
            font=theme.current().small, anchor="w", justify="left",
        )
        self.status_label.pack(side="left", padx=(5, 0))

        self.detail_label = tk.Label(
            outer, text="", bg=theme.CARD, fg=theme.DANGER,
            font=theme.current().tiny, wraplength=560, justify="left",
        )
        self.detail_label.pack(fill="x", pady=(4, 0))

        buttons = tk.Frame(outer, bg=theme.CARD)
        buttons.pack(fill="x", side="bottom", pady=(16, 0))
        self.cancel_button = secondary_button(buttons, "Cancel", self._close)
        self.cancel_button.pack(side="right")
        self.connect_button = primary_button(buttons, "Connect", self._connect, padx=22)
        self.connect_button.pack(side="right", padx=(0, 8))

    def _focus_first(self) -> None:
        (self.secret_entry if self.client_id_var.get() else self.client_id_entry).focus_set()

    # -- existing token --------------------------------------------------

    def _load_existing(self) -> None:
        client_id, client_secret = self.app.auth.credentials()
        if client_id:
            self.client_id_var.set(client_id)
        if client_secret:
            self.secret_var.set(client_secret)
        status = self.app.auth.status()
        if status.present and status.refresh_valid:
            self.status_dot.configure(fg=theme.SUCCESS)
            self.status_label.configure(text=status.summary, fg=theme.SUCCESS)
        elif status.present:
            self.status_dot.configure(fg=theme.DANGER)
            self.status_label.configure(text=status.summary, fg=theme.DANGER)

    # -- actions ---------------------------------------------------------

    def _toggle_secret(self) -> None:
        self.secret_entry.configure(show="" if self.show_var.get() else "•")

    def _client_id(self) -> str:
        return self.client_id_var.get().strip()

    def _open_sign_in(self) -> None:
        client_id = self._client_id()
        if not client_id:
            self._error("Enter your DigiKey Client ID first.")
            self.client_id_entry.focus_set()
            return
        try:
            url, state = self.app.auth.build_sign_in(client_id)
        except AuthError as exc:
            self._error(str(exc))
            return
        self._state = state
        self._signin_url = url
        try:
            webbrowser.open(url)
        except Exception as exc:  # pragma: no cover - browser integration
            logger.warning("Could not open the browser: %s", exc)
        self._status("Sign-in page opened. After authorizing, copy the localhost URL here.", theme.ACCENT)
        self.redirect_entry.focus_set()

    def _copy_sign_in(self) -> None:
        url = getattr(self, "_signin_url", "")
        if not url:
            self._error("Open the DigiKey sign-in page first, then copy the link.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
        except tk.TclError:
            pass
        self._status("Sign-in link copied to the clipboard.", theme.ACCENT)

    def _connect(self) -> None:
        client_id = self._client_id()
        client_secret = self.secret_var.get()
        redirect = self.redirect_var.get().strip()
        if not client_id:
            self._error("Enter your DigiKey Client ID.")
            self.client_id_entry.focus_set()
            return
        if not client_secret:
            self._error("Enter your DigiKey Client secret.")
            self.secret_entry.focus_set()
            return
        if not redirect:
            self._error("Paste the callback URL from your browser.")
            self.redirect_entry.focus_set()
            return

        self._set_busy(True)
        self._status("Connecting to DigiKey…", theme.ACCENT)
        self._state_for_worker = self._state
        self._thread = threading.Thread(
            target=self._exchange_worker,
            args=(client_id, client_secret, redirect),
            daemon=True,
            name="digikey-auth",
        )
        self._thread.start()
        self.after(50, self._poll)

    def _exchange_worker(self, client_id: str, client_secret: str, redirect: str) -> None:
        try:
            token = self.app.auth.complete_sign_in(
                client_id,
                client_secret,
                redirect,
                expected_state=self._state_for_worker,
                timeout=self.app.settings.http_timeout,
            )
        except BaseException as exc:  # reported on the Tk thread
            self._queue.put(("error", exc))
        else:
            self._queue.put(("ok", token))

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            if self._thread is not None and self._thread.is_alive():
                self.after(50, self._poll)
            else:
                self._set_busy(False)
            return

        if kind == "ok":
            self._set_busy(False)
            status = self.app.auth.status()
            self.status_dot.configure(fg=theme.SUCCESS)
            self.status_label.configure(text=status.summary, fg=theme.SUCCESS)
            self.detail_label.configure(text="")
            self.app.on_token_changed()
            if self.on_success is not None:
                self._closed = True
                self.destroy()
                self.on_success(payload)
                return
            self._status("Connected. You can close this dialog.", theme.SUCCESS)
        else:
            self._set_busy(False)
            self._error_from_exception(payload)

    # -- status ----------------------------------------------------------

    def _error_from_exception(self, exc: BaseException) -> None:
        if isinstance(exc, AppError):
            message = str(exc)
            details = exc.details
        else:  # pragma: no cover - unexpected
            message = f"Authentication failed: {exc}"
            details = ""
            logger.exception("Unexpected authentication failure")
        self._error(message)
        self.detail_label.configure(text=details or "")

    def _error(self, message: str) -> None:
        self.status_dot.configure(fg=theme.DANGER)
        self.status_label.configure(text=message, fg=theme.DANGER)

    def _status(self, message: str, colour: str) -> None:
        self.status_dot.configure(fg=colour)
        self.status_label.configure(text=message, fg=colour)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (self.client_id_entry, self.secret_entry, self.redirect_entry,
                       self.signin_button, self.copy_button):
            widget.configure(state=state)
        self.connect_button.configure(state=state)
        self.connect_button.configure(bg="#7ba7cf" if busy else theme.ACCENT)

    # -- closing ---------------------------------------------------------

    def _close(self) -> None:
        self._closed = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
