"""Main application window: toolbar, tabs, search, detail and database views."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import version
from gui import theme, utils
from gui.database_tab import DatabaseTab
from gui.dialogs.about_dialog import AboutDialog
from gui.dialogs.auth_dialog import AuthDialog
from gui.dialogs.batch_dialog import BatchDialog
from gui.dialogs.settings_dialog import SettingsDialog
from gui.widgets import Pill, icon_button, primary_button, secondary_button
from gui.widgets.banner import Banner
from gui.widgets.detail_panel import DetailPanel
from gui.widgets.param_table import show_parameters_dialog
from gui.widgets.results_table import ResultsTable
from kicad_core.errors import AppError, AuthRequired
from kicad_core.models import ProductInfo
from services.config import sync_folder_name
from services.database_service import DatabaseInfo

logger = logging.getLogger(__name__)


def _shorten(path: str, limit: int = 46) -> str:
    text = str(path)
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):]


class MainWindow:
    def __init__(self, root: tk.Tk, app):
        self.root = root
        self.app = app
        self.products: list[ProductInfo] = []
        self.selected_product: ProductInfo | None = None
        self.existing_product: ProductInfo | None = None
        self.db_info: DatabaseInfo | None = None
        self._toast_job: str | None = None

        self.container = tk.Frame(root, bg=theme.BG)
        self.container.pack(fill="both", expand=True)

        self._build_menu()
        self._build_toolbar()
        self._build_tabs()
        self.banner = Banner(self.container, before=self.tabs_bar)
        self._build_status_bar()
        self._build_pages()
        self._bind_shortcuts()
        self._select_tab("search")
        self.refresh_token_status()
        if app.db_info is not None:
            self.update_db_info(app.db_info)
        else:
            self.update_db_info(None)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open database…", accelerator="Ctrl+O",
                              command=self.open_database_dialog)
        file_menu.add_command(label="New database…", accelerator="Ctrl+N",
                              command=self.new_database_dialog)
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent databases", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Batch import…", accelerator="Ctrl+B",
                              command=self.open_batch_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.app.close)
        menubar.add_cascade(label="File", menu=file_menu)
        self.file_menu = file_menu

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Authenticate DigiKey…", command=self.open_auth_dialog)
        tools_menu.add_command(label="Settings…", command=self.open_settings_dialog)
        tools_menu.add_separator()
        tools_menu.add_command(label="Refresh database", accelerator="F5",
                               command=self.refresh_database)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About KiCad LibGen", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menubar)
        self._refresh_recent_menu()

    def _build_toolbar(self) -> None:
        toolbar = tk.Frame(self.container, bg=theme.BG, padx=14, pady=8)
        toolbar.pack(fill="x")

        chip = tk.Frame(toolbar, bg=theme.CARD, highlightbackground=theme.BORDER,
                        highlightthickness=1, padx=10, pady=5)
        chip.pack(side="left")
        icon = tk.Label(chip, bg=theme.CARD)
        icon.pack(side="left", padx=(0, 8))
        from gui import assets

        db_icon = assets.load_icon("database", self.root)
        if db_icon is not None:
            icon.configure(image=db_icon)
            icon.image = db_icon  # type: ignore[attr-defined]

        text = tk.Frame(chip, bg=theme.CARD)
        text.pack(side="left")
        self.db_name_label = tk.Label(text, text="No database", bg=theme.CARD,
                                      fg=theme.TEXT, font=theme.current().heading)
        self.db_name_label.pack(anchor="w")
        self.db_path_label = tk.Label(text, text="Open or create a database",
                                      bg=theme.CARD, fg=theme.MUTED,
                                      font=theme.current().tiny)
        self.db_path_label.pack(anchor="w")
        self.db_count_pill = Pill(chip, "0 parts", fg=theme.TEXT_SOFT)
        self.db_count_pill.pack(side="left", padx=(12, 2))

        self.open_button = secondary_button(toolbar, "Open…", self.open_database_dialog,
                                            icon="open")
        self.open_button.pack(side="left", padx=(10, 0))
        self.new_button = secondary_button(toolbar, "New…", self.new_database_dialog,
                                           icon="new")
        self.new_button.pack(side="left", padx=(6, 0))

        self.settings_button = icon_button(toolbar, "gear", self.open_settings_dialog,
                                            tooltip="Settings")
        self.settings_button.pack(side="right", padx=(6, 0))
        self.auth_button = secondary_button(toolbar, "Authenticate", self.open_auth_dialog,
                                            icon="key")
        self.auth_button.pack(side="right", padx=(6, 0))
        self.batch_button = secondary_button(toolbar, "Batch import", self.open_batch_dialog,
                                             icon="batch")
        self.batch_button.pack(side="right")

    def _build_tabs(self) -> None:
        self.tabs_bar = tk.Frame(self.container, bg=theme.BG, padx=14)
        self.tabs_bar.pack(fill="x")

        self.tab_buttons: dict[str, dict[str, Any]] = {}
        search_tab = self._make_tab("search", "Search DigiKey")
        search_tab["frame"].pack(side="left")
        database_tab = self._make_tab("database", "Database")
        database_tab["frame"].pack(side="left", padx=(6, 0))
        self.db_tab_badge = Pill(database_tab["body"], "0", fg=theme.TEXT_SOFT)
        self.db_tab_badge.pack(side="left", padx=(4, 0))
        self.db_tab_badge.bind("<Button-1>", lambda _event: self._select_tab("database"))

        token_frame = tk.Frame(self.tabs_bar, bg=theme.BG)
        token_frame.pack(side="right")
        self.token_dot = tk.Label(token_frame, text="●", bg=theme.BG, fg=theme.FAINT,
                                  font=theme.current().small)
        self.token_dot.pack(side="left")
        self.token_label = tk.Label(token_frame, text="Not signed in", bg=theme.BG,
                                    fg=theme.MUTED, font=theme.current().small)
        self.token_label.pack(side="left", padx=(5, 0))

        tk.Frame(self.container, bg=theme.BORDER, height=1).pack(fill="x")

    def _make_tab(self, key: str, text: str) -> dict[str, Any]:
        frame = tk.Frame(self.tabs_bar, bg=theme.BG, cursor="hand2")
        body = tk.Frame(frame, bg=theme.BG)
        body.pack(fill="x")
        label = tk.Label(body, text=text, bg=theme.BG, fg=theme.MUTED,
                         font=theme.current().heading, padx=6, pady=5, cursor="hand2")
        label.pack(side="left")
        underline = tk.Frame(frame, bg=theme.BG, height=2)
        underline.pack(fill="x")
        info = {"frame": frame, "body": body, "label": label, "underline": underline}
        for widget in (frame, body, label):
            widget.bind("<Button-1>", lambda _event, tab=key: self._select_tab(tab))
        self.tab_buttons[key] = info
        return info

    def _add_tab_badge(self, tab: dict[str, Any], pill: Pill | None) -> None:
        if pill is not None:
            pill.pack(side="left", padx=(4, 0))
    def _select_tab(self, key: str) -> None:
        self.active_tab = key
        for name, info in self.tab_buttons.items():
            active = name == key
            info["label"].configure(fg=theme.ACCENT if active else theme.MUTED)
            info["underline"].configure(bg=theme.ACCENT if active else theme.BG)
        if key == "database":
            self.database_tab.refresh()
        self.pages[key].tkraise()

    def _build_pages(self) -> None:
        self.content = tk.Frame(self.container, bg=theme.BG)
        self.content.pack(fill="both", expand=True)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.pages["search"] = self._build_search_page()
        self.database_tab = DatabaseTab(
            self.content,
            self.app,
            on_open_db=self.open_database_dialog,
            on_new_db=self.new_database_dialog,
        )
        self.pages["database"] = self.database_tab
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _build_search_page(self) -> tk.Frame:
        page = tk.Frame(self.content, bg=theme.BG)

        search_card = tk.Frame(page, bg=theme.CARD, highlightbackground=theme.BORDER,
                               highlightthickness=1, padx=16, pady=8)
        search_card.pack(fill="x", padx=14, pady=(8, 6))
        tk.Label(search_card, text="SEARCH DIGIKEY", bg=theme.CARD, fg=theme.MUTED,
                 font=(theme.current().family, 8, "bold")).pack(anchor="w")
        row = tk.Frame(search_card, bg=theme.CARD)
        row.pack(fill="x", pady=(3, 0))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(row, textvariable=self.search_var,
                                      font=(theme.current().family, 11))
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", lambda _event: self.perform_search())
        self.search_button = primary_button(row, "Search", self.perform_search,
                                            icon="search", padx=24, pady=5)
        self.search_button.pack(side="left", padx=(8, 0))
        tk.Label(
            search_card,
            text="Tip: exact manufacturer part numbers return the fewest variants.",
            bg=theme.CARD, fg=theme.MUTED, font=theme.current().tiny,
        ).pack(anchor="w", pady=(4, 0))

        self.paned = ttk.PanedWindow(page, orient="vertical")
        self.paned.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        results_card = tk.Frame(self.paned, bg=theme.CARD,
                                highlightbackground=theme.BORDER, highlightthickness=1)
        results_header = tk.Frame(results_card, bg=theme.CARD, padx=16, pady=6)
        results_header.pack(fill="x")
        tk.Label(results_header, text="Search results", bg=theme.CARD, fg=theme.TEXT,
                 font=(theme.current().family, 12, "bold")).pack(side="left")
        self.results_pill = Pill(results_header, "0 found", fg=theme.MUTED)
        self.results_pill.pack(side="left", padx=(10, 0))
        tk.Label(results_header, text="Sort: Relevance", bg=theme.CARD, fg=theme.FAINT,
                 font=theme.current().tiny).pack(side="right")
        tk.Frame(results_card, bg=theme.BORDER, height=1).pack(fill="x")
        self.results_table = ResultsTable(results_card, on_select=self.on_result_selected)
        self.results_table.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.paned.add(results_card, weight=3)

        detail_card = tk.Frame(self.paned, bg=theme.CARD,
                               highlightbackground=theme.BORDER, highlightthickness=1)
        self.detail = DetailPanel(
            detail_card,
            on_save=self.save_detail,
            on_clear=self.clear_detail,
            on_open_url=self.open_url,
            on_show_params=lambda product: show_parameters_dialog(self.root, product),
        )
        self.detail.pack(fill="both", expand=True)
        self.paned.add(detail_card, weight=2)

        self.root.after(120, self._init_sash)
        return page

    def _init_sash(self) -> None:
        self._fit_detail_pane()

    def _fit_detail_pane(self) -> None:
        try:
            self.root.update_idletasks()
            height = self.paned.winfo_height()
            if height > 320:
                self.paned.sashpos(0, max(150, height - 248))
        except (tk.TclError, IndexError):  # pragma: no cover
            pass

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self.container, bg=theme.CARD, highlightbackground=theme.BORDER,
                       highlightthickness=1)
        bar.pack(side="bottom", fill="x")
        inner = tk.Frame(bar, bg=theme.CARD, padx=14, pady=6)
        inner.pack(fill="x")

        self.status_dot = tk.Label(inner, text="●", bg=theme.CARD, fg=theme.FAINT,
                                   font=theme.current().small)
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(inner, text="No database open", bg=theme.CARD,
                                    fg=theme.MUTED, font=theme.current().small)
        self.status_text.pack(side="left", padx=(5, 16))
        self.status_file = tk.Label(inner, text="", bg=theme.CARD, fg=theme.MUTED,
                                    font=theme.current().small)
        self.status_file.pack(side="left", padx=(0, 16))
        self.status_count = tk.Label(inner, text="", bg=theme.CARD, fg=theme.MUTED,
                                     font=theme.current().small)
        self.status_count.pack(side="left", padx=(0, 16))
        self.status_params = tk.Label(inner, text="", bg=theme.CARD, fg=theme.MUTED,
                                      font=theme.current().small)
        self.status_params.pack(side="left")

        self.status_token = tk.Label(inner, text="Not signed in", bg=theme.CARD,
                                     fg=theme.MUTED, font=theme.current().small)
        self.status_token.pack(side="right", padx=(12, 0))
        self.status_version = tk.Label(inner, text=f"v{version.__version__}",
                                       bg=theme.CARD, fg=theme.FAINT,
                                       font=theme.current().tiny)
        self.status_version.pack(side="right")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _event: self.open_database_dialog())
        self.root.bind("<Control-O>", lambda _event: self.open_database_dialog())
        self.root.bind("<Control-n>", lambda _event: self.new_database_dialog())
        self.root.bind("<Control-N>", lambda _event: self.new_database_dialog())
        self.root.bind("<Control-b>", lambda _event: self.open_batch_dialog())
        self.root.bind("<Control-B>", lambda _event: self.open_batch_dialog())
        self.root.bind("<Control-f>", lambda _event: self.focus_search())
        self.root.bind("<Control-F>", lambda _event: self.focus_search())
        self.root.bind("<Control-l>", lambda _event: self.focus_search())
        self.root.bind("<Control-L>", lambda _event: self.focus_search())
        self.root.bind("<Control-s>", lambda _event: self.save_detail())
        self.root.bind("<Control-S>", lambda _event: self.save_detail())
        self.root.bind("<F5>", lambda _event: self.refresh_database())
        self.root.bind("<Escape>", self._on_escape)

    def _on_escape(self, _event=None) -> None:
        if self.banner.visible:
            self.banner.hide()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def open_database_dialog(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open a KiCad components database",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.app.open_database(path, create=False)
        except AppError as exc:
            self.show_banner(str(exc), exc.details, "error")
            return
        self._after_database_opened()

    def new_database_dialog(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Create a KiCad components database",
            defaultextension=".db",
            initialdir=str(Path(self.app.settings.database_path).parent),
            initialfile="components.db",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.app.open_database(path, create=True)
        except AppError as exc:
            self.show_banner(str(exc), exc.details, "error")
            return
        self._after_database_opened()

    def _after_database_opened(self) -> None:
        info = self.app.db_info
        if info is None:
            return
        sync = sync_folder_name(info.path)
        if sync:
            self.show_banner(
                f"This database is inside {sync}. Sync clients can lock or corrupt "
                "SQLite files; consider moving it to a local folder such as "
                "~/KiCadLibGen.",
                "",
                "warning",
            )
        else:
            self.clear_banner()
        self.toast(f"Opened {Path(info.path).name} ({info.count} records).")
        self._refresh_recent_menu()

    def refresh_database(self) -> None:
        info = self.app.refresh_db_info()
        if info is not None:
            self.update_db_info(info)
        self.refresh_token_status()
        self.toast("Database refreshed.")

    def update_db_info(self, info: DatabaseInfo | None) -> None:
        self.db_info = info
        if info is None:
            self.db_name_label.configure(text="No database")
            self.db_path_label.configure(text="Open or create a database")
            self.db_count_pill.set("0 parts")
            self.db_tab_badge.set("0")
            self.status_dot.configure(fg=theme.FAINT)
            self.status_text.configure(text="No database open", fg=theme.MUTED)
            self.status_file.configure(text="")
            self.status_count.configure(text="")
            self.status_params.configure(text="")
            self.database_tab.show_empty_state(
                "Open or create a database to browse its records."
            )
            self.detail.set_suggestions([], [])
            self.root.title(f"{version.APP_NAME} - {version.APP_SUBTITLE}")
            return

        name = Path(info.path).name
        folder = str(Path(info.path).parent)
        self.db_name_label.configure(text=name)
        self.db_path_label.configure(text=_shorten(folder))
        count_text = f"{info.count} part{'s' if info.count != 1 else ''}"
        self.db_count_pill.set(count_text)
        self.db_tab_badge.set(str(info.count))
        self.status_dot.configure(fg=theme.SUCCESS)
        self.status_text.configure(text="Database ready", fg=theme.SUCCESS)
        self.status_file.configure(text=name)
        self.status_count.configure(text=count_text)
        self.status_params.configure(text=f"{info.parameter_count:,} parameter rows")
        self.root.title(f"{version.APP_NAME} - {name}")
        try:
            symbols = self.app.database.distinct_symbols() if self.app.database else []
            footprints = self.app.database.distinct_footprints() if self.app.database else []
        except AppError:
            symbols, footprints = [], []
        self.detail.set_suggestions(symbols, footprints)
        self.database_tab.refresh()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.delete(0, "end")
        recent = self.app.settings.recent_databases
        if not recent:
            self.recent_menu.add_command(label="(none)", state="disabled")
            return
        for path in recent:
            self.recent_menu.add_command(
                label=f"{Path(path).name}  —  {_shorten(path, 60)}",
                command=lambda item=path: self._open_recent(item),
            )

    def _open_recent(self, path: str) -> None:
        if not Path(path).exists():
            self.show_banner(f"Database not found: {path}", "", "warning")
            return
        try:
            self.app.open_database(path, create=False)
        except AppError as exc:
            self.show_banner(str(exc), exc.details, "error")
            return
        self._after_database_opened()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def focus_search(self) -> None:
        self._select_tab("search")
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")

    def perform_search(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            self._select_tab("search")
            self.search_entry.focus_set()
            return
        if self.app.runner.busy:
            self.toast("Wait for the current operation to finish.")
            return
        self._select_tab("search")
        status = self.app.auth.status()
        if not status.present or not status.refresh_valid:
            self.open_auth_dialog(on_success=lambda _token: self.perform_search())
            return

        self.clear_banner()
        self._set_search_busy(True)
        self.status_text.configure(text="Searching DigiKey…", fg=theme.ACCENT)
        self.results_pill.set("searching…", fg=theme.ACCENT)
        submitted = self.app.runner.submit(
            lambda: self.app.search_service.search(query),
            self._search_succeeded,
            self._search_failed,
            name="search",
        )
        if not submitted:
            self._set_search_busy(False)

    def _search_succeeded(self, products: list[ProductInfo]) -> None:
        self._set_search_busy(False)
        self.products = products
        self.results_table.set_products(products)
        self.results_pill.set(f"{len(products)} found",
                              fg=theme.SUCCESS if products else theme.MUTED)
        self.status_text.configure(
            text="Database ready" if self.db_info is not None else "No database open",
            fg=theme.SUCCESS if self.db_info is not None else theme.MUTED,
        )
        self.refresh_token_status()
        if products:
            self.on_result_selected(products[0])
        if not products:
            self.detail.clear()
            self.selected_product = None
            self.existing_product = None
            self.show_banner(
                "No products matched that search. Try the manufacturer part number "
                "or fewer keywords.",
                "",
                "info",
            )

    def _search_failed(self, exc: BaseException) -> None:
        self._set_search_busy(False)
        self.results_pill.set("0 found", fg=theme.MUTED)
        self.status_text.configure(text="Search failed", fg=theme.DANGER)
        if isinstance(exc, AuthRequired):
            self.show_banner(str(exc), getattr(exc, "details", ""), "warning")
            self.open_auth_dialog(on_success=lambda _token: self.perform_search())
            return
        if isinstance(exc, AppError):
            self.show_banner(str(exc), exc.details, "error")
        else:
            logger.exception(
                "Unexpected search failure",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            self.show_banner(f"Search failed: {exc}", "", "error")

    def _set_search_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.search_button.configure(state=state,
                                     text="Searching…" if busy else "Search")
        self.batch_button.configure(state=state)
        self.open_button.configure(state=state)
        self.new_button.configure(state=state)

    def on_result_selected(self, product: ProductInfo | None) -> None:
        if product is None:
            self.selected_product = None
            self.existing_product = None
            self.detail.clear()
            return
        self.selected_product = product
        existing = None
        if self.app.database is not None:
            try:
                existing = self.app.database.find_by_mpn(product.mpn)
            except AppError as exc:
                self.show_banner(str(exc), exc.details, "error")
        self.existing_product = existing
        self.detail.set_product(product, in_database=existing is not None,
                                existing=existing)
        self._fit_detail_pane()

    def clear_detail(self) -> None:
        self.selected_product = None
        self.existing_product = None
        self.detail.clear()
        selection = self.results_table.tree.selection()
        if selection:
            self.results_table.tree.selection_remove(*selection)

    def save_detail(self) -> None:
        product = self.detail.product
        if product is None:
            return
        if self.app.database is None:
            if messagebox.askyesno(
                "No database open",
                "A database is required to save parts. Create one now?",
                parent=self.root,
            ):
                self.new_database_dialog()
            return

        symbol, footprint = self.detail.current_mapping()
        candidate = product.copy().with_mapping(symbol, footprint)
        existing = None
        try:
            existing = self.app.database.find_by_mpn(candidate.mpn)
        except AppError as exc:
            self.show_banner(str(exc), exc.details, "error")
            return
        if existing is not None:
            if not messagebox.askyesno(
                "Update existing part?",
                f"{candidate.mpn} already exists in the database.\n\n"
                "Overwrite its record and KiCad mapping?",
                parent=self.root,
            ):
                return
        self.detail.set_busy(True)
        try:
            outcome = self.app.database.upsert(candidate)
        except AppError as exc:
            self.show_banner(str(exc), exc.details, "error")
            self.detail.show_error(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected save failure")
            self.show_banner(f"Could not save the part: {exc}", "", "error")
            return
        finally:
            self.detail.set_busy(False)

        verb = "Added" if outcome.action == "inserted" else "Updated"
        message = (
            f"{verb} {candidate.mpn} in {Path(self.app.db_info.path).name}."
            if self.app.db_info
            else f"{verb} {candidate.mpn}."
        )
        if outcome.rows_updated > 1:
            message += f" Updated {outcome.rows_updated} legacy duplicate rows."
        self.toast(message)
        info = self.app.refresh_db_info()
        if info is not None:
            self.update_db_info(info)
        self.refresh_token_status()
        stored = self.app.database.find_by_mpn(candidate.mpn) if self.app.database else None
        self.detail.set_product(candidate, in_database=True, existing=stored or candidate)
        self.existing_product = stored

    def open_url(self, url: str) -> None:
        if not utils.open_url(url):
            self.show_banner(f"Could not open {url}", "", "warning")

    # ------------------------------------------------------------------
    # Dialog actions
    # ------------------------------------------------------------------

    def open_auth_dialog(self, on_success=None) -> None:
        AuthDialog(self.root, self.app, on_success=on_success)

    def open_batch_dialog(self) -> None:
        if self.app.database is None:
            self.show_banner("Open or create a database before importing a batch.",
                             "", "info")
            return
        BatchDialog(self.root, self.app, on_finished=self._batch_finished)

    def _batch_finished(self, summary) -> None:
        info = self.app.refresh_db_info()
        if info is not None:
            self.update_db_info(info)
        self.refresh_token_status()
        if summary.log_path:
            self.toast(f"Batch finished. Log: {Path(summary.log_path).name}")

    def open_settings_dialog(self) -> None:
        SettingsDialog(self.root, self.app)

    def show_about(self) -> None:
        AboutDialog(self.root)

    # ------------------------------------------------------------------
    # Status / banner / toast
    # ------------------------------------------------------------------

    def refresh_token_status(self) -> None:
        status = self.app.auth.status()
        if not status.present:
            text, colour = "Not signed in", theme.MUTED
        elif not status.refresh_valid:
            text, colour = "Sign-in expired", theme.DANGER
        elif status.access_valid:
            text, colour = status.summary, theme.SUCCESS
        else:
            text, colour = status.summary, theme.WARNING
        self.token_dot.configure(fg=colour)
        self.token_label.configure(text=text, fg=colour)
        self.status_token.configure(text=text, fg=colour)
        self.auth_button.configure(text="Sign in" if not status.present else "Authenticate")

    def show_banner(self, message: str, details: str = "", kind: str = "error") -> None:
        self.banner.show(message, details or "", kind)

    def clear_banner(self) -> None:
        self.banner.hide()

    def toast(self, message: str) -> None:
        self.status_text.configure(text=message, fg=theme.TEXT_SOFT)
        if self._toast_job is not None:
            try:
                self.root.after_cancel(self._toast_job)
            except tk.TclError:
                pass
        self._toast_job = self.root.after(4500, self._restore_status)

    def _restore_status(self) -> None:
        self._toast_job = None
        if self.db_info is not None:
            self.status_text.configure(text="Database ready", fg=theme.SUCCESS)
        else:
            self.status_text.configure(text="No database open", fg=theme.MUTED)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def on_close(self) -> None:
        if self._toast_job is not None:
            try:
                self.root.after_cancel(self._toast_job)
            except tk.TclError:
                pass
