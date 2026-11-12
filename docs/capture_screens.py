"""Dev helper: build a demo DB, open the app and capture screenshots."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO = ROOT / ".tmp_demo"
DEMO.mkdir(exist_ok=True)
CONFIG = DEMO / "config"
CONFIG.mkdir(exist_ok=True)
LOG = DEMO / "logs"
LOG.mkdir(exist_ok=True)
os.environ["KICAD_LIB_GEN_CONFIG_DIR"] = str(CONFIG)
os.environ["KICAD_LIB_GEN_LOG_DIR"] = str(LOG)

from kicad_core.parser import parse_digikey_response  # noqa: E402
from services.database_service import DatabaseService  # noqa: E402


def payload(mpn, manufacturer, description, qty, status, price, package, category):
    return {
        "ManufacturerProductNumber": mpn,
        "Manufacturer": {"Name": manufacturer},
        "Description": {
            "ProductDescription": description,
            "DetailedDescription": f"{manufacturer} {description}",
        },
        "ProductStatus": {"Status": status},
        "QuantityAvailable": qty,
        "ProductVariations": [{
            "DigiKeyProductNumber": f"{mpn}-ND",
            "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": price}],
        }],
        "Parameters": [
            {"ParameterId": 1, "ParameterText": "Package / Case",
             "ValueText": package, "ParameterType": "String"},
            {"ParameterId": 2, "ParameterText": "Mounting Type",
             "ValueText": "Surface Mount", "ParameterType": "String"},
            {"ParameterId": 3, "ParameterText": "Operating Temperature",
             "ValueText": "-40°C ~ 85°C", "ParameterType": "String"},
            {"ParameterId": 4, "ParameterText": "Voltage - Supply",
             "ValueText": "3V ~ 32V", "ParameterType": "String"},
        ],
        "Category": {"Name": category, "ChildCategories": []},
        "ProductUrl": f"https://www.digikey.com/en/products/detail/{mpn}",
        "DatasheetUrl": "https://example.invalid/datasheet.pdf",
    }


def build_db():
    db_path = DEMO / "components.db"
    if db_path.exists():
        db_path.unlink()
    service = DatabaseService(db_path)
    service.open_or_create(create=True)
    for index in range(120):
        mpn = f"RC0603FR-07{index:03d}KL"
        product = parse_digikey_response(payload(
            mpn, "Yageo", f"RES {index}K OHM 1% 1/10W 0603", str(index * 37),
            "Active", "0.0021", "0603 (1608 Metric)", "Resistors",
        ))
        product.with_mapping("Resistor_SMD:R_0603_1608Metric",
                             "Resistor_SMD:R_0603_1608Metric")
        service.upsert(product)
    for index in range(8):
        mpn = f"GRM188R71C104KA{index:02d}D"
        product = parse_digikey_response(payload(
            mpn, "Murata", "CAP CER 0.1UF 16V X7R 0603", "12000", "Active",
            "0.0047", "0603 (1608 Metric)", "Capacitors",
        ))
        product.with_mapping("Capacitor_SMD:C_0603_1608Metric",
                             "Capacitor_SMD:C_0603_1608Metric")
        service.upsert(product)
    print("demo db", db_path, service.count())
    (DEMO / "parts.csv").write_text(
        "manufacturer_product_number,kicad_symbol_library,kicad_footprint_library\n"
        "LM324N,Symbol:IC_LM324N,Footprint:IC_LM324N\n"
        "LM2902N,Symbol:IC_LM2902N,Footprint:IC_LM2902N\n"
        "LM324DR,Symbol:IC_LM324_DR,Footprint:IC_LM324_DR\n"
        "STM32F103C8T6,Symbol:IC_STM32F103C8T6,Footprint:IC_STM32F103C8T6\n"
        "ATMEGA328P-AU,Symbol:IC_ATMEGA328P,Footprint:IC_ATMEGA328P\n",
        encoding="utf-8-sig",
    )
    return db_path


def make_products():
    specs = [
        ("LM324N", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", 2500, "Active", 0.45, "14-DIP (0.300\", 7.62mm)", "Integrated Circuits (ICs)"),
        ("LM324NE4", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", 1800, "Active", 0.42, "14-DIP (0.300\", 7.62mm)", "Integrated Circuits (ICs)"),
        ("LM324NP", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", 0, "Obsolete", 0.61, "14-DIP (0.300\", 7.62mm)", "Integrated Circuits (ICs)"),
        ("LM2902N", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", 4212, "Active", 0.38, "14-DIP (0.300\", 7.62mm)", "Integrated Circuits (ICs)"),
        ("LM324DR", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14SOIC", 15000, "Active", 0.29, "14-SOIC (0.154\", 3.90mm)", "Integrated Circuits (ICs)"),
    ]
    return [parse_digikey_response(payload(*spec)) for spec in specs]


def main():
    db_path = build_db()
    from PIL import ImageGrab

    from gui.app import App
    from gui.dialogs.auth_dialog import AuthDialog
    from gui.dialogs.batch_dialog import BatchDialog
    from gui.dialogs.settings_dialog import SettingsDialog

    app = App(portable=False, database_path=str(db_path))
    products = make_products()
    docs = ROOT / "docs"

    def grab(widget, name):
        try:
            widget.update_idletasks()
            widget.update()
            x = widget.winfo_rootx()
            y = widget.winfo_rooty()
            w = widget.winfo_width()
            h = widget.winfo_height()
            image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            image.save(docs / name)
            print("saved", name, image.size)
        except Exception as exc:
            print("capture failed", name, exc)

    def capture_main():
        app.window.root.lift()
        app.window.root.attributes("-topmost", True)
        app.window.clear_banner()
        app.window.search_var.set("LM324N")
        app.window._search_succeeded(products)
        app.window.root.after(500, lambda: (
            grab(app.root, "screenshot-main.png"),
            capture_database(),
        ))

    def capture_database():
        app.window._select_tab("database")
        app.window.database_tab.filter_var.set("")
        app.window.database_tab.refresh()
        tab = app.window.database_tab
        if tab.records:
            tab.tree.selection_set("0")
            tab.tree.focus("0")
            tab._on_select()
        app.window.root.after(300, lambda: (
            grab(app.root, "screenshot-database.png"),
            capture_auth(),
        ))

    def capture_auth():
        app.window._select_tab("search")
        dialog = AuthDialog(app.root, app)
        dialog.geometry("+120+80")
        app.root.after(400, lambda: (
            grab(dialog, "screenshot-auth.png"),
            dialog.destroy(),
            capture_batch(),
        ))

    def capture_batch():
        dialog = BatchDialog(app.root, app)
        dialog.geometry("+100+40")
        dialog.load_file(str(DEMO / "parts.csv"))
        app.root.after(400, lambda: (
            grab(dialog, "screenshot-batch.png"),
            dialog.destroy(),
            capture_settings(),
        ))

    def capture_settings():
        dialog = SettingsDialog(app.root, app)
        dialog.geometry("+160+60")
        app.root.after(400, lambda: (
            grab(dialog, "screenshot-settings.png"),
            dialog.destroy(),
            finish(),
        ))

    def finish():
        app.close()

    app.root.after(1200, capture_main)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
