"""Read-only dialog listing a product's 32 DigiKey parameters."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui import theme
from kicad_core.models import ProductInfo


def show_parameters_dialog(parent: tk.Misc, product: ProductInfo) -> tk.Toplevel:
    window = tk.Toplevel(parent)
    window.title(f"Parameters - {product.base.manufacturer_product_number}")
    window.configure(bg=theme.BG)
    window.transient(parent.winfo_toplevel())
    window.geometry("640x460")
    window.minsize(440, 300)

    header = tk.Frame(window, bg=theme.CARD, padx=16, pady=12,
                      highlightbackground=theme.BORDER, highlightthickness=1)
    header.pack(fill="x", padx=14, pady=(14, 8))
    tk.Label(
        header, text=product.base.manufacturer_product_number, bg=theme.CARD,
        fg=theme.TEXT, font=(theme.current().family, 13, "bold"),
    ).pack(anchor="w")
    tk.Label(
        header,
        text=f"{product.parameter_count()} parameters reported by DigiKey",
        bg=theme.CARD, fg=theme.MUTED, font=theme.current().small,
    ).pack(anchor="w", pady=(2, 0))

    body = tk.Frame(window, bg=theme.CARD, highlightbackground=theme.BORDER,
                    highlightthickness=1)
    body.pack(fill="both", expand=True, padx=14, pady=(0, 10))

    tree = ttk.Treeview(body, columns=("name", "value"), show="headings",
                        selectmode="browse")
    tree.heading("name", text="PARAMETER", anchor="w")
    tree.heading("value", text="VALUE", anchor="w")
    tree.column("name", width=220, minwidth=120, anchor="w")
    tree.column("value", width=360, minwidth=160, anchor="w", stretch=True)
    scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
    scroll.pack(side="right", fill="y", pady=8, padx=(0, 4))

    for index, (name, value) in enumerate(product.parameter_pairs()):
        tree.insert("", "end", iid=str(index), values=(name, value))
    if not product.parameter_count():
        tree.insert("", "end", values=("No parameters reported", ""))

    footer = tk.Frame(window, bg=theme.BG)
    footer.pack(fill="x", padx=14, pady=(0, 14))
    ttk.Button(footer, text="Close", command=window.destroy).pack(side="right")

    window.bind("<Escape>", lambda _event: window.destroy())
    window.focus_set()
    return window
