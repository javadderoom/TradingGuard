"""
TradingGuard — Application Entry Point
Launches the PyQt6 GUI with the dark theme.
"""

import sys
import os
import logging

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

# Add the project root to sys.path so 'app' package is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ui.main_window import MainWindow



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


def load_stylesheet() -> str:
    """Read the QSS file from the ui/ directory."""
    qss_path = os.path.join(
        os.path.dirname(__file__), "ui", "styles.qss"
    )
    with open(qss_path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    app = QApplication(sys.argv)

    # Apply dark stylesheet
    app.setStyleSheet(load_stylesheet())

    # Set a decent default font
    font = QFont("Segoe UI")
    font.setPixelSize(14)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
