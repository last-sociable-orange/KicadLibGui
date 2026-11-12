"""Results treeview with status colouring and an empty state."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gui import theme
from kicad_core.models import ProductInfo


def _format_qty(value: str) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return value or "-"


def _status_tag(status: str) -> str:
    upper = (status or "").upper()
    if upper == "ACTIVE":
        return "status-active"
    if upper in ("NOTRECOMMENDED", "OBSOLETE", "DISCONTINUED", "END OF LIFE"):
        return "status-obsolete"
    return "status-other"


class ResultsTable(tk.Frame):
    COLUMNS = (
        ("mpn", "MPN", 170, "w"),
        ("manufacturer", "MANUFACTURER", 150, "w"),
        ("description", "DESCRIPTION", 420, "w"),
        ("qty", "QTY", 80, "e"),
        ("status", "STATUS", 100, "w"),
    )

    def __init__(self, parent: tk.Misc, *, on_select: Callable[[ProductInfo | None], None] | None = None):
        super().__init__(parent, bg=theme.CARD)
        self.on_select = on_select
        self.products: list[ProductInfo] = []

        self.tree = ttk.Treeview(
            self,
            columns=[column[0] for column in self.COLUMNS],
            show="headings",
            selectmode="browse",
        )
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, minwidth=60, anchor=anchor,
                             stretch=(key == "description"))
        self.tree.tag_configure("status-active", foreground=theme.TEXT)
        self.tree.tag_configure("status-obsolete", foreground=theme.DANGER)
        self.tree.tag_configure("status-other", foreground=theme.WARNING)

        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        self.empty = tk.Label(
            self,
            text="Search DigiKey to see parts here.",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.current().base,
            justify="center",
        )
        self.empty.place(relx=0.5, rely=0.55, anchor="center")

        self.tree.bind("<<TreeviewSelect>>", self._handle_select)
        self.tree.bind("<Double-1>", lambda _event: self._handle_select())

    # -- data ------------------------------------------------------------

    def set_products(self, products: list[ProductInfo]) -> None:
        self.products = list(products)
        self.tree.delete(*self.tree.get_children())
        for index, product in enumerate(self.products):
            base = product.base
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    base.manufacturer_product_number or "-",
                    base.manufacturer or "-",
                    base.description or "-",
                    _format_qty(base.qty_available),
                    base.part_status or "-",
                ),
                tags=(_status_tag(base.part_status),),
            )
        if self.products:
            self.empty.place_forget()
            self.tree.selection_set("0")
            self.tree.focus("0")
        else:
            self.empty.configure(text="No matching parts found.\nTry a more specific part number.")
            self.empty.place(relx=0.5, rely=0.55, anchor="center")

    def clear(self, message: str = "Search DigiKey to see parts here.") -> None:
        self.products = []
        self.tree.delete(*self.tree.get_children())
        self.empty.configure(text=message)
        self.empty.place(relx=0.5, rely=0.55, anchor="center")
        if self.on_select:
            self.on_select(None)

    def selected_product(self) -> ProductInfo | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return self.products[int(selection[0])]
        except (ValueError, IndexError):
            return None

    def select_index(self, index: int) -> None:
        if 0 <= index < len(self.products):
            self.tree.selection_set(str(index))
            self.tree.focus(str(index))
            self.tree.see(str(index))

    # -- events ----------------------------------------------------------

    def _handle_select(self, _event=None) -> None:
        if self.on_select:
            self.on_select(self.selected_product())
