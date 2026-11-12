"""Selected-part detail panel: overview, datasheet links and KiCad mapping."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gui import theme
from gui.widgets import Pill, link_label, primary_button, secondary_button, separator
from kicad_core.models import ProductInfo


class DetailPanel(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_save: Callable[[], None],
        on_clear: Callable[[], None],
        on_open_url: Callable[[str], None],
        on_show_params: Callable[[ProductInfo], None],
    ):
        super().__init__(parent, bg=theme.CARD, padx=14, pady=4)
        self._on_save = on_save
        self._on_clear = on_clear
        self._on_open_url = on_open_url
        self._on_show_params = on_show_params
        self.product: ProductInfo | None = None
        self.in_database = False

        self.empty = tk.Label(
            self,
            text="Select a search result to see details\nand set its KiCad symbol and footprint.",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.current().base,
            justify="center",
        )
        self.empty.pack(fill="both", expand=True, pady=60)

        self.content = tk.Frame(self, bg=theme.CARD)
        self.content.pack(fill="both", expand=True)

        self._build_header()
        separator(self.content, bg=theme.BORDER, pady=(4, 0))
        self._build_body()

        self.clear()

    # -- construction ----------------------------------------------------

    def _build_header(self) -> None:
        header = tk.Frame(self.content, bg=theme.CARD)
        header.pack(fill="x")
        header.grid_columnconfigure(0, weight=1)

        left = tk.Frame(header, bg=theme.CARD)
        left.grid(row=0, column=0, sticky="w")

        title_row = tk.Frame(left, bg=theme.CARD)
        title_row.pack(anchor="w")
        self.mpn_label = tk.Label(
            title_row, text="", bg=theme.CARD, fg=theme.TEXT,
            font=(theme.current().family, 13, "bold"),
        )
        self.mpn_label.pack(side="left")
        self.manufacturer_label = tk.Label(
            title_row, text="", bg=theme.CARD, fg=theme.MUTED,
            font=theme.current().small,
        )
        self.manufacturer_label.pack(side="left", padx=(10, 0), pady=(3, 0))
        self.badge = Pill(title_row, "NOT IN DATABASE", fg=theme.WARNING, bg=theme.WARNING_BG)
        self.badge.pack(side="left", padx=(12, 0), pady=(3, 0))

        links = tk.Frame(header, bg=theme.CARD)
        links.grid(row=0, column=1, sticky="ne")
        self.datasheet_link = link_label(
            links, "Datasheet ↗", lambda: self._open_link(self._url("datasheet"))
        )
        self.datasheet_link.pack(side="left", padx=(0, 14))
        self.product_link = link_label(
            links, "Product page ↗", lambda: self._open_link(self._url("product"))
        )
        self.product_link.pack(side="left")

    def _build_body(self) -> None:
        body = tk.Frame(self.content, bg=theme.CARD)
        body.pack(fill="both", expand=True, pady=(4, 0))
        body.grid_columnconfigure(0, weight=1, uniform="detail")
        body.grid_columnconfigure(1, weight=1, uniform="detail")
        body.grid_rowconfigure(0, weight=1)

        overview = tk.Frame(body, bg=theme.CARD)
        overview.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        mapping = tk.Frame(body, bg=theme.CARD)
        mapping.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        divider = tk.Frame(body, bg=theme.BORDER, width=1)
        divider.grid(row=0, column=0, sticky="nse", padx=(0, 0))

        self._build_overview(overview)
        self._build_mapping(mapping)

    def _build_overview(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=theme.CARD)
        header.pack(fill="x", pady=(0, 3))
        tk.Label(
            header, text="OVERVIEW", bg=theme.CARD, fg=theme.MUTED,
            font=(theme.current().family, 8, "bold"),
        ).pack(side="left")
        self.params_link = link_label(
            header, "View all", self._show_params, fg=theme.ACCENT,
            font=theme.current().tiny,
        )
        self.params_link.pack(side="right")
        self.params_label = tk.Label(
            header, text="", bg=theme.CARD, fg=theme.MUTED,
            font=theme.current().tiny,
        )
        self.params_label.pack(side="right", padx=(0, 6))

        grid = tk.Frame(parent, bg=theme.CARD)
        grid.pack(fill="x", anchor="nw")
        grid.grid_columnconfigure(0, weight=1, uniform="ov")
        grid.grid_columnconfigure(1, weight=1, uniform="ov")

        self.values: dict[str, tk.Label] = {}
        layout = (
            (("manufacturer", "Manufacturer"), ("status", "Part status")),
            (("package", "Package"), ("digikey_pn", "DigiKey PN")),
            (("category", "Category"), ("price", "Unit price")),
        )
        for row_index, pair in enumerate(layout):
            for col_index, (key, title) in enumerate(pair):
                cell = tk.Frame(grid, bg=theme.CARD)
                cell.grid(row=row_index, column=col_index, sticky="nw",
                          padx=(0, 10) if col_index == 0 else 0, pady=0)
                tk.Label(
                    cell, text=title, bg=theme.CARD, fg=theme.MUTED,
                    font=theme.current().tiny, width=10, anchor="w",
                ).pack(side="left", anchor="n")
                value = tk.Label(
                    cell, text="-", bg=theme.CARD, fg=theme.TEXT,
                    font=theme.current().small, anchor="w", justify="left",
                    wraplength=175,
                )
                value.pack(side="left", fill="x", expand=True, anchor="n")
                self.values[key] = value

    def _build_mapping(self, parent: tk.Frame) -> None:
        tk.Label(
            parent, text="KICAD MAPPING", bg=theme.CARD, fg=theme.MUTED,
            font=(theme.current().family, 8, "bold"),
        ).pack(anchor="w", pady=(0, 3))

        symbol_row = tk.Frame(parent, bg=theme.CARD)
        symbol_row.pack(fill="x", pady=(0, 3))
        tk.Label(
            symbol_row, text="Symbol", bg=theme.CARD, fg=theme.TEXT_SOFT,
            font=theme.current().tiny, width=9, anchor="w",
        ).pack(side="left", anchor="n", pady=(7, 0))
        self.symbol_var = tk.StringVar()
        self.symbol_combo = ttk.Combobox(
            symbol_row, textvariable=self.symbol_var, width=36,
            font=theme.current().small, style="Compact.TCombobox",
        )
        self.symbol_combo.pack(side="left", fill="x", expand=True)

        footprint_row = tk.Frame(parent, bg=theme.CARD)
        footprint_row.pack(fill="x", pady=(0, 2))
        tk.Label(
            footprint_row, text="Footprint", bg=theme.CARD, fg=theme.TEXT_SOFT,
            font=theme.current().tiny, width=9, anchor="w",
        ).pack(side="left", anchor="n", pady=(7, 0))
        self.footprint_var = tk.StringVar()
        self.footprint_combo = ttk.Combobox(
            footprint_row, textvariable=self.footprint_var, width=36,
            font=theme.current().small, style="Compact.TCombobox",
        )
        self.footprint_combo.pack(side="left", fill="x", expand=True)

        hint = tk.Frame(parent, bg=theme.CARD)
        hint.pack(fill="x", pady=(0, 4))
        tk.Label(
            hint, text="ⓘ", bg=theme.CARD, fg=theme.MUTED,
            font=theme.current().tiny,
        ).pack(side="left")
        tk.Label(
            hint,
            text="Use ? in place of the MPN; it is replaced when you save.",
            bg=theme.CARD, fg=theme.MUTED, font=theme.current().tiny,
        ).pack(side="left", padx=(5, 0))

        actions = tk.Frame(parent, bg=theme.CARD)
        actions.pack(fill="x", side="bottom")
        self.clear_button = secondary_button(actions, "Clear", self._clear_clicked,
                                             pady=2, font=theme.current().small)
        self.clear_button.pack(side="left")
        self.save_button = primary_button(actions, "Add to database", self._on_save,
                                          padx=16, pady=3,
                                          font=(theme.current().family, 9, "bold"))
        self.save_button.pack(side="right")

    # -- data ------------------------------------------------------------

    def set_suggestions(self, symbols: list[str], footprints: list[str]) -> None:
        def uniq(values: list[str]) -> list[str]:
            seen: list[str] = []
            for value in values:
                if value and value not in seen:
                    seen.append(value)
            return seen

        self.symbol_combo.configure(
            values=uniq(["Symbol:?"] + list(symbols) + ["Standard:"])
        )
        self.footprint_combo.configure(
            values=uniq(["Footprint:?"] + list(footprints) + ["Standard:"])
        )

    def set_product(
        self,
        product: ProductInfo,
        *,
        in_database: bool,
        existing: ProductInfo | None = None,
    ) -> None:
        self.product = product
        self.in_database = in_database
        self.empty.pack_forget()
        self.content.pack(fill="both", expand=True)

        base = product.base
        self.mpn_label.configure(text=base.manufacturer_product_number or "(unnamed)")
        self.manufacturer_label.configure(text=base.manufacturer or "")
        if in_database:
            self.badge.set("IN DATABASE", fg=theme.SUCCESS, bg=theme.SUCCESS_BG)
            self.save_button.configure(text="Update database", bg=theme.ACCENT)
        else:
            self.badge.set("NOT IN DATABASE", fg=theme.WARNING, bg=theme.WARNING_BG)
            self.save_button.configure(text="Add to database", bg=theme.ACCENT)

        self.values["manufacturer"].configure(text=base.manufacturer or "-")
        self.values["package"].configure(text=base.package or "-")
        self.values["category"].configure(text=base.main_category or "-")
        self.values["status"].configure(
            text=base.part_status or "-",
            fg=self._status_colour(base.part_status),
        )
        self.values["digikey_pn"].configure(text=base.distributor_product_number or "-")
        self.values["price"].configure(text=base.unit_price or "-")

        source = existing if existing is not None else product
        self.symbol_var.set(source.base.kicad_symbol_library or "")
        self.footprint_var.set(source.base.kicad_footprint_library or "")

        count = product.parameter_count()
        self.params_label.configure(
            text=f"{count} parameter{'s' if count != 1 else ''}"
        )
        self._set_links(base.datasheet_url, base.product_url)

    def clear(self) -> None:
        self.product = None
        self.in_database = False
        self.content.pack_forget()
        self.empty.pack(fill="both", expand=True, pady=60)
        self.symbol_var.set("")
        self.footprint_var.set("")

    def current_mapping(self) -> tuple[str, str]:
        return self.symbol_var.get().strip(), self.footprint_var.get().strip()

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (self.symbol_combo, self.footprint_combo):
            widget.configure(state=state)
        self.save_button.configure(state=state)
        self.clear_button.configure(state=state)
        if busy:
            self.save_button.configure(bg="#7ba7cf")

    def focus_mapping(self) -> None:
        self.symbol_combo.focus_set()

    def show_error(self, message: str) -> None:
        # The window owns the banner; this is a visual hint on the panel.
        self.save_button.configure(bg=theme.DANGER)
        self.after(1200, lambda: self.save_button.configure(bg=theme.ACCENT))

    # -- helpers ---------------------------------------------------------

    def _clear_clicked(self) -> None:
        self._on_clear()

    def _show_params(self) -> None:
        if self.product is not None:
            self._on_show_params(self.product)
    def _url(self, kind: str) -> str:
        if self.product is None:
            return ""
        base = self.product.base
        return base.datasheet_url if kind == "datasheet" else base.product_url

    def _open_link(self, url: str) -> None:
        if url:
            self._on_open_url(url)

    def _set_links(self, datasheet: str, product: str) -> None:
        self.datasheet_link.configure(fg=theme.ACCENT if datasheet else theme.FAINT)
        self.product_link.configure(fg=theme.ACCENT if product else theme.FAINT)
        self.datasheet_link.configure(cursor="hand2" if datasheet else "")
        self.product_link.configure(cursor="hand2" if product else "")
        self.datasheet_link._link_fg = theme.ACCENT if datasheet else theme.FAINT  # type: ignore[attr-defined]
        self.product_link._link_fg = theme.ACCENT if product else theme.FAINT  # type: ignore[attr-defined]

    @staticmethod
    def _status_colour(status: str) -> str:
        upper = (status or "").upper()
        if upper == "ACTIVE":
            return theme.SUCCESS
        if upper in ("NOTRECOMMENDED", "OBSOLETE", "DISCONTINUED"):
            return theme.DANGER
        return theme.WARNING
