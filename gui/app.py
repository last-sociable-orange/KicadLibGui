"""Application composition root: settings, services, Tk root, main window."""

from __future__ import annotations

import logging
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

import version
from gui import assets, theme
from gui.main_window import MainWindow
from gui.worker import TaskRunner
from kicad_core.errors import AppError, AuthError
from services.auth_service import AuthService
from services.config import Settings, legacy_token_candidates, sync_folder_name
from services.database_service import DatabaseInfo, DatabaseService
from services.logging_setup import setup_logging
from services.search_service import SearchService

logger = logging.getLogger(__name__)


class App:
    def __init__(self, *, portable: bool | None = None, database_path: str | None = None):
        theme.enable_dpi_awareness()

        self.settings = Settings.load(portable=portable)
        if database_path:
            self.settings.database_path = str(Path(database_path).expanduser())
        setup_logging(self.settings.log_level, portable=self.settings.portable)
        logger.info("Starting %s %s", version.APP_NAME, version.__version__)

        self.root = self._create_window()
        self.theme = theme.current()
        self.root.geometry("1120x820")
        self.root.minsize(900, 620)
        self.root.title(f"{version.APP_NAME} - {version.APP_SUBTITLE}")
        self._center_window()
        self._set_icon()

        self.auth = AuthService(self.settings.token_path)
        self.search_service = SearchService(
            self.auth,
            limit=self.settings.search_limit,
            timeout=self.settings.http_timeout,
        )
        self.database: DatabaseService | None = None
        self.db_info: DatabaseInfo | None = None

        self.runner = TaskRunner(self.root, max_workers=3)
        self.root.report_callback_exception = self._report_callback_exception

        self.window = MainWindow(self.root, self)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.root.deiconify()
        self.root.after(120, self._startup)
        self.root.after(500, self._refresh_token_after_startup)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    @staticmethod
    def _create_window() -> tk.Tk:
        """Create the Tk root, retrying transient Tcl/Tk library I/O errors.

        Cloud-synced Python installs occasionally leave `init.tcl` or
        `ttk.tcl` temporarily unreadable; a second attempt usually succeeds
        and is much friendlier than a traceback on launch.
        """
        last_error: BaseException | None = None
        for attempt in range(4):
            root = None
            try:
                root = tk.Tk()
                root.withdraw()
                theme.apply(root)
                return root
            except tk.TclError as exc:
                last_error = exc
                logger.warning("Tk initialisation attempt %s failed: %s", attempt + 1, exc)
                if root is not None:
                    try:
                        root.destroy()
                    except tk.TclError:
                        pass
                time.sleep(0.25)
        assert last_error is not None
        raise last_error

    def _center_window(self) -> None:
        self.root.update_idletasks()
        try:
            width, height = 1120, 820
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 2 - 20)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:  # pragma: no cover
            pass

    def _set_icon(self) -> None:
        icon = assets.load_app_icon(self.root)
        if icon is not None:
            try:
                self.root.iconphoto(True, icon)
                self._icon_image = icon
            except tk.TclError:  # pragma: no cover
                pass

    def _startup(self) -> None:
        self._maybe_import_legacy_token()
        path = self.settings.database_path
        if path and Path(path).exists():
            try:
                self.open_database(path, create=False, remember=False)
            except AppError as exc:
                logger.warning("Could not reopen last database: %s", exc)
                self.window.show_banner(
                    f"Could not reopen {Path(path).name}: {exc}",
                    getattr(exc, "details", ""),
                    "warning",
                )
            else:
                sync = sync_folder_name(path)
                if sync:
                    self.window.show_banner(
                        f"This database is inside {sync}. Sync clients can lock or "
                        "corrupt SQLite files; consider moving it to a local folder "
                        "such as ~/KiCadLibGen.",
                        "",
                        "warning",
                    )
        else:
            self.window.update_db_info(None)

    def _maybe_import_legacy_token(self) -> None:
        if self.auth.exists():
            return
        for candidate in legacy_token_candidates():
            if not candidate.exists():
                continue
            try:
                accepted = messagebox.askyesno(
                    "Import DigiKey token?",
                    f"An existing DigiKey token was found at:\n\n{candidate}\n\n"
                    "Import it into the KiCad LibGen configuration folder?",
                    parent=self.root,
                )
            except tk.TclError:  # pragma: no cover
                accepted = False
            if not accepted:
                return
            try:
                destination = self.auth.import_legacy(candidate)
                logger.info("Imported legacy token into %s", destination)
                self.on_token_changed()
            except (AuthError, OSError) as exc:
                logger.warning("Legacy token import failed: %s", exc)
                self.window.show_banner(
                    "Could not import the existing DigiKey token.",
                    getattr(exc, "details", ""),
                    "warning",
                )
            return

    def _refresh_token_after_startup(self) -> None:
        self.window.refresh_token_status()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def open_database(self, path: str | Path, *, create: bool = False,
                      remember: bool = True) -> DatabaseInfo:
        service = DatabaseService(path)
        info = service.open_or_create(create=create)
        self.database = service
        self.db_info = info
        if remember:
            self.settings.add_recent(info.path)
            self.settings.save()
            self.window._refresh_recent_menu()
        self.window.update_db_info(info)
        logger.info("Database ready: %s (%s records)", info.path, info.count)
        return info

    def refresh_db_info(self) -> DatabaseInfo | None:
        if self.database is None:
            return None
        try:
            info = self.database.open_or_create(create=False)
        except AppError as exc:
            self.window.show_banner(str(exc), getattr(exc, "details", ""), "error")
            return None
        self.db_info = info
        return info

    # ------------------------------------------------------------------
    # Settings / token
    # ------------------------------------------------------------------

    def apply_settings(self, previous_token_path: str | None = None) -> None:
        self.settings.save()
        logging.getLogger().setLevel(
            getattr(logging, self.settings.log_level.upper(), logging.INFO)
        )
        if previous_token_path is None or previous_token_path != self.settings.token_path:
            self.auth = AuthService(self.settings.token_path)
        self.search_service = SearchService(
            self.auth,
            limit=self.settings.search_limit,
            timeout=self.settings.http_timeout,
        )
        self.window.refresh_token_status()

        database_path = self.settings.database_path
        if database_path and Path(database_path).exists():
            if self.database is None or str(self.database.path) != str(Path(database_path)):
                try:
                    self.open_database(database_path, create=False, remember=False)
                except AppError as exc:
                    self.window.show_banner(
                        str(exc), getattr(exc, "details", ""), "warning"
                    )
        logger.info("Settings applied")

    def on_token_changed(self) -> None:
        self.window.refresh_token_status()

    # ------------------------------------------------------------------
    # UI helpers used by tabs/dialogs
    # ------------------------------------------------------------------

    def show_banner(self, message: str, details: str = "", kind: str = "error") -> None:
        self.window.show_banner(message, details, kind)

    def toast(self, message: str) -> None:
        self.window.toast(message)

    # ------------------------------------------------------------------
    # Shutdown / errors
    # ------------------------------------------------------------------

    def _report_callback_exception(self, exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error("Unhandled GUI exception:\n%s", text)
        try:
            self.window.show_banner(
                f"Unexpected error: {exc_value}",
                text,
                "error",
            )
        except Exception:  # pragma: no cover - last resort
            pass

    def close(self) -> None:
        logger.info("Closing %s", version.APP_NAME)
        try:
            self.window.on_close()
        except Exception:  # pragma: no cover
            pass
        try:
            self.runner.shutdown()
        except Exception:  # pragma: no cover
            pass
        try:
            self.root.destroy()
        except tk.TclError:  # pragma: no cover
            pass

    def run(self) -> int:
        try:
            self.root.mainloop()
        finally:
            try:
                self.runner.shutdown()
            except Exception:
                pass
        return 0
