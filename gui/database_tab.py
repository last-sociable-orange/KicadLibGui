"""Database tab: browse/filter records, edit mapping, delete, duplicate report."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from gui import theme, utils
from gui.widgets import Pill, link_label, primary_button, secondary_button
from kicad_core.errors import AppError
from kicad_core.models import ProductInfo
from services.database_service import RecordSummary

logger = logging.getLogger(__name__)


class DatabaseTab(tk.Frame):
    def __init__(self, parent: tk.Misc, app,
                 on_open_db: Callable[[], None], on_new_db: Callable[[], None]):
        super().__init__(parent, bg=theme.BG)
        self.app = app
        self._on_open_db = on_open_db
        self._on_new_db = on_new_db
        self.records: list[RecordSummary] = []
        self.current: RecordSummary | None = None
        self.current_product: ProductInfo | None = None
        self._duplicates: list[tuple[str, int]] = []

        self._build()
        self.show_empty_state("Open or create a database to browse its records.")

    # -- layout ----------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(
            self, bg=theme.CARD, padx=16, pady=12,
            highlightbackground=theme.BORDER, highlightthickness=1,
        )
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))

        title_row = tk.Frame(header, bg=theme.CARD)
        title_row.pack(fill="x")
        tk.Label(title_row, text="Database records", bg=theme.CARD, fg=theme.TEXT,
                 font=(theme.current().family, 12, "bold")).pack(side="left")
        self.count_pill = Pill(title_row, "0 records", fg=theme.TEXT_SOFT)
        self.count_pill.pack(side="left", padx=(10, 0))
        self.duplicate_link = link_label(
            title_row, "", self._show_duplicates, fg=theme.WARNING,
        )
        self.duplicate_link.pack(side="left", padx=(10, 0))
        self.duplicate_link.pack_forget()

        filter_row = tk.Frame(header, bg=theme.CARD)
        filter_row.pack(fill="x", pady=(10, 0))
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(filter_row, textvariable=self.filter_var,
                                      font=theme.current().base)
        self.filter_entry.pack(side="left", fill="x", expand=True)
        self.filter_entry.bind("<Return>", lambda _event: self.refresh())
        secondary_button(filter_row, "Search", self.refresh, icon="search").pack(
            side="left", padx=(8, 0)
        )
        secondary_button(filter_row, "Refresh", self.refresh, icon="refresh").pack(
            side="left", padx=(8, 0)
        )

        # Records table ---------------------------------------------------
        table_card = tk.Frame(self, bg=theme.CARD, highlightbackground=theme.BORDER,
                              highlightthickness=1)
        table_card.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))

        self.tree = ttk.Treeview(
            table_card,
            columns=("mpn", "manufacturer", "description", "symbol", "footprint", "status"),
            show="headings",
            selectmode="browse",
        )
        for key, title, width, anchor in (
            ("mpn", "MPN", 190, "w"),
            ("manufacturer", "MANUFACTURER", 140, "w"),
            ("description", "DESCRIPTION", 300, "w"),
            ("symbol", "SYMBOL", 220, "w"),
            ("footprint", "FOOTPRINT", 220, "w"),
            ("status", "STATUS", 90, "w"),
        ):
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, minwidth=60, anchor=anchor,
                             stretch=(key == "description"))
        scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        xscroll.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.empty = tk.Frame(table_card, bg=theme.CARD)
        self.empty_label = tk.Label(
            self.empty, text="", bg=theme.CARD, fg=theme.MUTED,
            font=theme.current().base, justify="center",
        )
        self.empty_label.pack(pady=(0, 10))
        button_row = tk.Frame(self.empty, bg=theme.CARD)
        button_row.pack()
        secondary_button(button_row, "Open database…", self._on_open_db).pack(side="left")
        secondary_button(button_row, "Create database…", self._on_new_db).pack(
            side="left", padx=(8, 0)
        )

        # Edit panel ------------------------------------------------------
        self.editor = tk.Frame(self, bg=theme.CARD, padx=16, pady=12,
                               highlightbackground=theme.BORDER, highlightthickness=1)
        self.editor.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        self.editor.grid_remove()

        top = tk.Frame(self.editor, bg=theme.CARD)
        top.pack(fill="x")
        left = tk.Frame(top, bg=theme.CARD)
        left.pack(side="left", fill="x", expand=True)
        self.editor_mpn = tk.Label(left, text="", bg=theme.CARD, fg=theme.TEXT,
                                   font=(theme.current().family, 12, "bold"))
        self.editor_mpn.pack(anchor="w")
        self.editor_meta = tk.Label(left, text="", bg=theme.CARD, fg=theme.MUTED,
                                    font=theme.current().small)
        self.editor_meta.pack(anchor="w", pady=(2, 0))
        self.editor_datasheet = link_label(
            top, "Datasheet ↗", self._open_record_datasheet,
        )
        self.editor_datasheet.pack(side="right")

        mapping = tk.Frame(self.editor, bg=theme.CARD)
        mapping.pack(fill="x", pady=(10, 0))
        mapping.grid_columnconfigure(0, weight=1)
        mapping.grid_columnconfigure(1, weight=1)

        symbol_box = tk.Frame(mapping, bg=theme.CARD)
        symbol_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        tk.Label(symbol_box, text="Symbol library", bg=theme.CARD, fg=theme.TEXT_SOFT,
                 font=theme.current().small).pack(anchor="w")
        self.symbol_var = tk.StringVar()
        self.symbol_combo = ttk.Combobox(symbol_box, textvariable=self.symbol_var,
                                         font=theme.current().base)
        self.symbol_combo.pack(fill="x", pady=(3, 0))

        footprint_box = tk.Frame(mapping, bg=theme.CARD)
        footprint_box.grid(row=0, column=1, sticky="ew", padx=(12, 0))
        tk.Label(footprint_box, text="Footprint library", bg=theme.CARD,
                 fg=theme.TEXT_SOFT, font=theme.current().small).pack(anchor="w")
        self.footprint_var = tk.StringVar()
        self.footprint_combo = ttk.Combobox(footprint_box, textvariable=self.footprint_var,
                                            font=theme.current().base)
        self.footprint_combo.pack(fill="x", pady=(3, 0))

        actions = tk.Frame(self.editor, bg=theme.CARD)
        actions.pack(fill="x", pady=(12, 0))
        self.delete_button = secondary_button(actions, "Delete record", self._delete_record)
        self.delete_button.pack(side="left")
        self.save_button = primary_button(actions, "Save mapping", self._save_mapping,
                                          padx=18)
        self.save_button.pack(side="right")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _event: self.symbol_combo.focus_set())

        self._set_editor_visible(False)

    # -- state -----------------------------------------------------------

    def show_empty_state(self, message: str) -> None:
        self.empty_label.configure(text=message)
        self.empty.place(relx=0.5, rely=0.5, anchor="center")
        self.records = []
        self.tree.delete(*self.tree.get_children())
        self._set_editor_visible(False)
        self.count_pill.set("0 records")
        self.duplicate_link.pack_forget()
        self.filter_entry.configure(state="disabled")
        self._duplicates = []

    def refresh(self) -> None:
        database = self.app.database
        if database is None:
            self.show_empty_state("Open or create a database to browse its records.")
            return
        try:
            records = database.list_records(self.filter_var.get(), limit=1000)
            duplicates = database.duplicate_mpns()
            symbols = database.distinct_symbols()
            footprints = database.distinct_footprints()
        except AppError as exc:
            self.app.show_banner(str(exc), getattr(exc, "details", ""), "error")
            return

        self.filter_entry.configure(state="normal")
        self._duplicates = duplicates
        self.records = records
        self.tree.delete(*self.tree.get_children())
        for index, record in enumerate(records):
            self.tree.insert(
                "", "end", iid=str(index),
                values=(record.mpn or "-", record.manufacturer or "-",
                        record.description or "-", record.symbol or "-",
                        record.footprint or "-", record.status or "-"),
            )
        self.count_pill.set(f"{len(records)} record{'s' if len(records) != 1 else ''}")
        if duplicates:
            total = sum(count for _mpn, count in duplicates)
            self.duplicate_link.configure(text=f"{total} duplicate rows")
            self.duplicate_link.pack(side="left", padx=(10, 0))
        else:
            self.duplicate_link.pack_forget()

        self.symbol_combo.configure(values=self._unique(["Symbol:?"] + symbols + ["Standard:"]))
        self.footprint_combo.configure(values=self._unique(
            ["Footprint:?"] + footprints + ["Standard:"]
        ))
        self._set_editor_visible(False)
        self.current = None
        self.current_product = None
        if records:
            self.empty.place_forget()
            selection = self.tree.selection()
            if selection:
                self.tree.selection_remove(*selection)
        else:
            self.empty_label.configure(text="No records match the filter.")
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.append(value)
        return seen

    # -- selection -------------------------------------------------------

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection or self.app.database is None:
            self._set_editor_visible(False)
            return
        try:
            record = self.records[int(selection[0])]
        except (ValueError, IndexError):
            return
        self.current = record
        try:
            product = self.app.database.find_by_mpn(record.mpn)
        except AppError as exc:
            self.app.show_banner(str(exc), getattr(exc, "details", ""), "error")
            return
        self.current_product = product
        self._set_editor_visible(True)
        self.editor_mpn.configure(text=record.mpn or "(no MPN)")
        meta = " · ".join(part for part in (record.manufacturer, record.description) if part)
        self.editor_meta.configure(text=meta or "No metadata")
        if product is not None:
            self.symbol_var.set(product.base.kicad_symbol_library or "")
            self.footprint_var.set(product.base.kicad_footprint_library or "")
            self.editor_datasheet.configure(
                fg=theme.ACCENT if product.base.datasheet_url else theme.FAINT
            )
        else:
            self.symbol_var.set(record.symbol or "")
            self.footprint_var.set(record.footprint or "")

    def _set_editor_visible(self, visible: bool) -> None:
        if visible:
            self.editor.grid()
        else:
            self.editor.grid_remove()

    # -- actions ---------------------------------------------------------

    def _save_mapping(self) -> None:
        if self.current is None or self.app.database is None:
            return
        symbol = self.symbol_var.get().strip()
        footprint = self.footprint_var.get().strip()
        try:
            self.app.database.update_mapping(self.current.mpn, symbol, footprint)
        except AppError as exc:
            self.app.show_banner(str(exc), getattr(exc, "details", ""), "error")
            return
        self.app.toast(f"Saved mapping for {self.current.mpn}.")
        self.refresh()
        self.app.refresh_db_info()

    def _delete_record(self) -> None:
        if self.current is None or self.app.database is None:
            return
        if not messagebox.askyesno(
            "Delete record?",
            f"Delete {self.current.mpn} from the database?\n\n"
            "This only removes the row from components.db; it cannot be undone.",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            changed = self.app.database.delete(self.current.mpn)
        except AppError as exc:
            self.app.show_banner(str(exc), getattr(exc, "details", ""), "error")
            return
        self.app.toast(f"Deleted {changed} row{'s' if changed != 1 else ''} for {self.current.mpn}.")
        self.refresh()
        self.app.refresh_db_info()

    def _open_record_datasheet(self) -> None:
        if self.current_product and self.current_product.base.datasheet_url:
            utils.open_url(self.current_product.base.datasheet_url)

    def _show_duplicates(self) -> None:
        if not self._duplicates:
            return
        window = tk.Toplevel(self)
        window.title("Duplicate MPNs")
        window.configure(bg=theme.CARD)
        window.transient(self.winfo_toplevel())
        window.geometry("520x360")
        tk.Label(
            window,
            text="These part numbers appear more than once in components.db.\n"
                 "Duplicate rows are reported, never deleted automatically.",
            bg=theme.CARD, fg=theme.TEXT_SOFT, font=theme.current().small,
            justify="left", padx=16, pady=14,
        ).pack(anchor="w")
        tree = ttk.Treeview(window, columns=("mpn", "count"), show="headings")
        tree.heading("mpn", text="MANUFACTURER PRODUCT NUMBER", anchor="w")
        tree.heading("count", text="ROWS", anchor="e")
        tree.column("mpn", width=380, anchor="w")
        tree.column("count", width=60, anchor="e")
        for mpn, count in self._duplicates:
            tree.insert("", "end", values=(mpn, count))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        secondary_button(window, "Close", window.destroy).pack(pady=(0, 14))
