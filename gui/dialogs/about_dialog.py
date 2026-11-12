"""About dialog."""

from __future__ import annotations

import platform
import tkinter as tk

import version
from gui import theme, utils
from gui.widgets import link_label, primary_button


class AboutDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title(f"About {version.APP_NAME}")
        self.configure(bg=theme.CARD)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())

        outer = tk.Frame(self, bg=theme.CARD, padx=28, pady=24)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text=version.APP_NAME, bg=theme.CARD, fg=theme.TEXT,
                 font=(theme.current().family, 18, "bold")).pack(anchor="w")
        tk.Label(outer, text=version.APP_SUBTITLE, bg=theme.CARD, fg=theme.MUTED,
                 font=theme.current().base).pack(anchor="w", pady=(2, 14))

        tk.Label(
            outer,
            text=(
                "A small desktop front end for the kicad_lib_gen command line tool. "
                "Search DigiKey, map a part to a KiCad symbol and footprint, and "
                "store it in the existing components.db schema."
            ),
            bg=theme.CARD, fg=theme.TEXT_SOFT, font=theme.current().small,
            wraplength=460, justify="left",
        ).pack(anchor="w")

        details = tk.Frame(outer, bg=theme.CARD)
        details.pack(fill="x", pady=(16, 0))
        rows = (
            ("Version", version.__version__),
            ("Python", platform.python_version()),
            ("Tk", str(self.tk.call("info", "patchlevel"))),
            ("Platform", platform.platform()),
        )
        for index, (name, value) in enumerate(rows):
            tk.Label(details, text=name, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.current().small, width=10, anchor="w").grid(
                row=index, column=0, sticky="w", pady=1
            )
            tk.Label(details, text=value, bg=theme.CARD, fg=theme.TEXT,
                     font=theme.current().small, anchor="w").grid(
                row=index, column=1, sticky="w", pady=1
            )

        links = tk.Frame(outer, bg=theme.CARD)
        links.pack(fill="x", pady=(14, 0))
        link_label(links, "Upstream repository ↗",
                   lambda: utils.open_url(version.UPSTREAM_URL)).pack(side="left")

        footer = tk.Frame(outer, bg=theme.CARD)
        footer.pack(fill="x", pady=(20, 0))
        tk.Label(footer, text="MIT licence", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.current().tiny).pack(side="left")
        primary_button(footer, "Close", self.destroy, padx=20).pack(side="right")

        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth() + 20}x{self.winfo_reqheight() + 10}")
        try:
            self.grab_set()
        except tk.TclError:  # pragma: no cover
            pass
