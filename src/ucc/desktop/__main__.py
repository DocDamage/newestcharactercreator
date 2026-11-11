"""Launch the optional UCC PySide6 desktop application (never downloads software)."""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from .window import MainWindow
    except ImportError as exc:
        print("PySide6 is required. Install the opt-in desktop extra: ",
              'py -3 -m pip install -e ".[desktop]"', file=sys.stderr)
        print(f"Dependency detail: {exc}", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("UCC")
    app.setApplicationName("Universal Character Creator")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
