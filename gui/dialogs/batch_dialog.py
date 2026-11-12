"""Batch CSV import dialog: preview, options, progress, cancel, summary."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk

from gui import theme, utils
from gui.widgets import Pill, primary_button, secondary_button
from kicad_core.errors import AppError, BatchError
from services.batch_service import (
    BatchOptions,
    BatchProgress,
    BatchRunner,
    BatchSummary,
    CsvIssue,
    validate_csv,
)

logger = logging.getLogger(__name__)


class BatchDialog(tk.Toplevel):
    PREVIEW_LIMIT = 12

    def __init__(self, parent: tk.Misc, app, on_finished: Callable[[BatchSummary], None] | None = None):
        super().__init__(parent)
        self.app = app
        self.on_finished = on_finished
        self._validation = None
        self._summary: BatchSummary | None = None
        self._running = False
        self._close_requested = False
        self._finished = False

        self.title("Batch import from CSV")
        self.configure(bg=theme.CARD)
        self.transient(parent.winfo_toplevel())
        self.geometry("940x780")
        self.minsize(780, 640)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _event: self._close())

        self._build()
        self._set_running(False)
        try:
            self.grab_set()
        except tk.TclError:  # pragma: no cover
            pass

    # -- layout ----------------------------------------------------------

    def _build(self) -> None:
        outer = tk.Frame(self, bg=theme.CARD, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="Import parts from a CSV file", bg=theme.CARD,
                 fg=theme.TEXT, font=(theme.current().family, 15, "bold")).pack(anchor="w")
        tk.Label(
            outer,
            text="Header: manufacturer_product_number, kicad_symbol_library, kicad_footprint_library",
            bg=theme.CARD, fg=theme.MUTED, font=theme.current().small,
        ).pack(anchor="w", pady=(3, 14))

        file_row = tk.Frame(outer, bg=theme.CARD)
        file_row.pack(fill="x")
        tk.Label(file_row, text="CSV file", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w")
        picker = tk.Frame(file_row, bg=theme.CARD)
        picker.pack(fill="x", pady=(3, 0))
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(picker, textvariable=self.path_var,
                                     font=theme.current().base)
        self.path_entry.pack(side="left", fill="x", expand=True)
        self.browse_button = secondary_button(picker, "Browse…", self._browse)
        self.browse_button.pack(side="left", padx=(8, 0))

        preview_header = tk.Frame(outer, bg=theme.CARD)
        preview_header.pack(fill="x", pady=(14, 4))
        tk.Label(preview_header, text="PREVIEW", bg=theme.CARD, fg=theme.MUTED,
                 font=(theme.current().family, 8, "bold")).pack(side="left")
        self.preview_count = Pill(preview_header, "", fg=theme.MUTED)
        self.preview_count.pack(side="left", padx=(8, 0))

        preview_frame = tk.Frame(outer, bg=theme.CARD, highlightbackground=theme.BORDER,
                                 highlightthickness=1)
        preview_frame.pack(fill="both", expand=True)
        self.preview = ttk.Treeview(
            preview_frame, columns=("mpn", "symbol", "footprint"),
            show="headings", height=8, selectmode="none",
        )
        for key, title, width in (
            ("mpn", "MPN", 240),
            ("symbol", "SYMBOL", 300),
            ("footprint", "FOOTPRINT", 300),
        ):
            self.preview.heading(key, text=title, anchor="w")
            self.preview.column(key, width=width, anchor="w", stretch=(key != "mpn"))
        scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=scroll.set)
        self.preview.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll.pack(side="right", fill="y", pady=6, padx=(0, 4))

        self.validation_label = tk.Label(
            outer, text="Choose a CSV file to preview it.", bg=theme.CARD,
            fg=theme.MUTED, font=theme.current().small, anchor="w",
            justify="left", wraplength=860,
        )
        self.validation_label.pack(fill="x", pady=(6, 6))

        options = tk.Frame(outer, bg=theme.CARD)
        options.pack(fill="x", pady=(2, 10))
        self.skip_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.skip_check = ttk.Checkbutton(
            options, text="Skip duplicates", variable=self.skip_var,
            command=self._on_skip_toggle,
        )
        self.skip_check.pack(side="left")
        self.overwrite_check = ttk.Checkbutton(
            options, text="Overwrite existing mapping", variable=self.overwrite_var,
            command=self._on_overwrite_toggle,
        )
        self.overwrite_check.pack(side="left", padx=(18, 0))

        delay_box = tk.Frame(options, bg=theme.CARD)
        delay_box.pack(side="left", padx=(26, 0))
        tk.Label(delay_box, text="Delay", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(side="left")
        self.delay_var = tk.StringVar(value=str(self.app.settings.batch_delay_ms))
        self.delay_spin = tk.Spinbox(
            delay_box, from_=0, to=10000, increment=50, width=6,
            textvariable=self.delay_var, font=theme.current().small,
            relief="flat", highlightbackground=theme.BORDER_STRONG,
            highlightthickness=1, bg=theme.WHITE,
        )
        self.delay_spin.pack(side="left", padx=(6, 4))
        tk.Label(delay_box, text="ms", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.current().small).pack(side="left")

        progress_frame = tk.Frame(outer, bg=theme.CARD)
        progress_frame.pack(fill="x", pady=(4, 0))
        progress_header = tk.Frame(progress_frame, bg=theme.CARD)
        progress_header.pack(fill="x")
        tk.Label(progress_header, text="Progress", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(side="left")
        self.progress_count = tk.Label(
            progress_header, text="0 / 0", bg=theme.CARD, fg=theme.MUTED,
            font=theme.current().small,
        )
        self.progress_count.pack(side="right")
        self.progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=100,
            style="Accent.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", pady=(4, 4))
        self.counts_label = tk.Label(
            progress_frame, text="0 inserted · 0 skipped · 0 errors",
            bg=theme.CARD, fg=theme.MUTED, font=theme.current().small,
        )
        self.counts_label.pack(anchor="w")
        self.status_label = tk.Label(
            progress_frame, text="", bg=theme.CARD, fg=theme.MUTED,
            font=theme.current().small, anchor="w", justify="left", wraplength=860,
        )
        self.status_label.pack(fill="x", pady=(4, 0))

        buttons = tk.Frame(outer, bg=theme.CARD)
        buttons.pack(fill="x", pady=(14, 0))
        self.close_button = secondary_button(buttons, "Close", self._close)
        self.close_button.pack(side="right")
        self.cancel_button = secondary_button(buttons, "Cancel", self._cancel)
        self.cancel_button.pack(side="right", padx=(0, 8))
        self.open_log_button = secondary_button(buttons, "Open log", self._open_log)
        self.open_log_button.pack(side="left")
        self.open_log_button.pack_forget()
        self.start_button = primary_button(buttons, "Start", self._start, padx=26)
        self.start_button.pack(side="right", padx=(0, 8))

    # -- file handling ---------------------------------------------------

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose a batch CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        self.path_var.set(path)
        self._summary = None
        self.open_log_button.pack_forget()
        try:
            self._validation = validate_csv(path)
        except BatchError as exc:
            self._validation = None
            self._show_validation_error([CsvIssue(0, str(exc))])
            self._set_start_enabled(False)
            return
        self._populate_preview(self._validation)
        self._show_validation(self._validation)
        self._set_start_enabled(self._validation.valid)

    def _populate_preview(self, validation) -> None:
        self.preview.delete(*self.preview.get_children())
        for row in validation.rows[: self.PREVIEW_LIMIT]:
            self.preview.insert("", "end", values=(row.mpn, row.symbol or "-",
                                                   row.footprint or "-"))
        self.preview_count.set(f"{validation.total} rows")
        if not validation.rows:
            self.preview.insert("", "end", values=("No data rows", "", ""))

    def _show_validation(self, validation) -> None:
        errors = validation.errors
        warnings = validation.warnings
        if errors:
            first = errors[:3]
            text = " · ".join(f"Line {issue.line}: {issue.message}" if issue.line
                              else issue.message for issue in first)
            if len(errors) > len(first):
                text += f" · (+{len(errors) - len(first)} more)"
            self.validation_label.configure(text=text, fg=theme.DANGER)
        elif warnings:
            text = f"Ready to import {validation.total} rows. " + " ".join(
                f"Line {issue.line}: {issue.message}" for issue in warnings[:3]
            )
            self.validation_label.configure(text=text, fg=theme.WARNING)
        else:
            self.validation_label.configure(
                text=f"Ready to import {validation.total} rows.", fg=theme.SUCCESS
            )

    def _show_validation_error(self, issues: list[CsvIssue]) -> None:
        self.preview.delete(*self.preview.get_children())
        self.preview_count.set("0 rows")
        text = " · ".join(
            f"Line {issue.line}: {issue.message}" if issue.line else issue.message
            for issue in issues[:3]
        )
        self.validation_label.configure(text=text, fg=theme.DANGER)

    # -- options ---------------------------------------------------------

    def _on_skip_toggle(self) -> None:
        if self.skip_var.get() and self.overwrite_var.get():
            self.overwrite_var.set(False)

    def _on_overwrite_toggle(self) -> None:
        if self.overwrite_var.get() and self.skip_var.get():
            self.skip_var.set(False)

    # -- run -------------------------------------------------------------

    def _start(self) -> None:
        if self._running:
            return
        if self._validation is None or not self._validation.valid:
            self.status_label.configure(text="Fix the CSV errors before starting.",
                                        fg=theme.DANGER)
            return
        if self.app.database is None:
            self.status_label.configure(
                text="Open or create a database before importing.", fg=theme.DANGER
            )
            return
        try:
            delay = max(0, min(10000, int(float(self.delay_var.get()))))
        except ValueError:
            self.status_label.configure(text="Delay must be a number of milliseconds.",
                                        fg=theme.DANGER)
            return

        options = BatchOptions(
            skip_duplicates=self.skip_var.get(),
            overwrite_existing=self.overwrite_var.get(),
            delay_ms=delay,
            timeout=self.app.settings.http_timeout,
        )
        self._summary = None
        self._finished = False
        self.start_button.pack_forget()
        self.open_log_button.pack_forget()
        self._set_running(True)
        self.progress.configure(value=0, maximum=max(1, self._validation.total))
        self.progress_count.configure(text=f"0 / {self._validation.total}")
        self.counts_label.configure(text="0 inserted · 0 skipped · 0 errors")
        self.status_label.configure(text="Starting import…", fg=theme.MUTED)

        runner = BatchRunner(
            self.app.search_service,
            self.app.database,
            options,
            cancel_event=self.app.runner.cancel_event,
            on_progress=self.app.runner.post_progress,
        )
        self._runner = runner
        self.app.runner.set_progress_handler(self._on_progress)
        submitted = self.app.runner.submit(
            lambda: runner.run(self._validation),
            self._on_success,
            self._on_error,
            name="batch import",
        )
        if not submitted:
            self._set_running(False)
            self.status_label.configure(
                text="Another task is running. Wait for it to finish and retry.",
                fg=theme.DANGER,
            )

    def _on_progress(self, progress: BatchProgress) -> None:
        if not self.winfo_exists():
            return
        total = max(1, progress.total)
        self.progress.configure(maximum=total, value=progress.index)
        self.progress_count.configure(text=f"{progress.index} / {progress.total}")
        counts = progress.counts
        skipped = (counts.get("skipped_duplicates", 0)
                   + counts.get("skipped_no_result", 0)
                   + counts.get("skipped_multi_results", 0))
        inserted = counts.get("inserted", 0) + counts.get("updated", 0)
        self.counts_label.configure(
            text=f"{inserted} inserted/updated · {skipped} skipped · "
                 f"{counts.get('errors', 0)} errors · {counts.get('cancelled', 0)} cancelled"
        )
        self.status_label.configure(
            text=f"{progress.row.mpn}: {progress.status}", fg=theme.MUTED
        )

    def _on_success(self, summary: BatchSummary) -> None:
        self._summary = summary
        self._finished = True
        self._set_running(False)
        total = max(1, summary.total)
        self.progress.configure(maximum=total, value=summary.processed)
        self.progress_count.configure(text=f"{summary.processed} / {summary.total}")
        inserted = summary.count("inserted") + summary.count("updated")
        skipped = (summary.count("skipped_duplicates")
                   + summary.count("skipped_no_result")
                   + summary.count("skipped_multi_results"))
        self.counts_label.configure(
            text=f"{inserted} inserted/updated · {skipped} skipped · "
                 f"{summary.count('errors')} errors · {summary.count('cancelled')} cancelled"
        )
        if summary.aborted:
            status = f"Stopped: {summary.abort_reason}"
            colour = theme.DANGER if summary.count("errors") else theme.WARNING
        else:
            status = "Import finished."
            colour = theme.SUCCESS
        self.status_label.configure(text=status, fg=colour)
        if summary.log_path:
            self.open_log_button.pack(side="left")
        self.start_button.pack(side="right", padx=(0, 8))
        self.app.runner.set_progress_handler(None)
        if self.on_finished is not None:
            self.on_finished(summary)
        if self._close_requested:
            self._close()

    def _on_error(self, exc: BaseException) -> None:
        self._finished = True
        self._set_running(False)
        self.app.runner.set_progress_handler(None)
        message = str(exc) if isinstance(exc, AppError) else f"Import failed: {exc}"
        self.status_label.configure(text=message, fg=theme.DANGER)
        self.start_button.pack(side="right", padx=(0, 8))
        if self._close_requested:
            self._close()

    def _cancel(self) -> None:
        if not self._running:
            return
        self.app.runner.request_cancel()
        self.cancel_button.configure(state="disabled")
        self.status_label.configure(
            text="Cancelling after the current request…", fg=theme.WARNING
        )

    def _open_log(self) -> None:
        if self._summary and self._summary.log_path:
            utils.open_path(self._summary.log_path)

    # -- state -----------------------------------------------------------

    def _set_start_enabled(self, enabled: bool) -> None:
        self.start_button.configure(state="normal" if enabled else "disabled")
        self.start_button.configure(bg=theme.ACCENT if enabled else "#c7d7e8")

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        for widget in (self.browse_button, self.path_entry, self.skip_check,
                       self.overwrite_check, self.delay_spin):
            widget.configure(state=state)
        self.start_button.configure(state="disabled" if running else "normal")
        if running:
            self.cancel_button.configure(state="normal")
        else:
            self.cancel_button.configure(state="disabled")
        self.close_button.configure(text="Cancel" if running else "Close")
        if not running:
            self._set_start_enabled(self._validation is not None and self._validation.valid)

    # -- closing ---------------------------------------------------------

    def _close(self) -> None:
        if self._running:
            if not self._close_requested:
                if not messagebox.askyesno(
                    "Cancel import?",
                    "A batch import is running. Stop it after the current row?",
                    parent=self,
                ):
                    return
            self._close_requested = True
            self.app.runner.request_cancel()
            self.status_label.configure(
                text="Cancelling; the dialog will close when the current request finishes.",
                fg=theme.WARNING,
            )
            return
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
