import sys
import warnings
sys.dont_write_bytecode = True
warnings.filterwarnings("ignore", message=".*Failed to disconnect.*")
warnings.filterwarnings("ignore", category=RuntimeWarning)

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GBSturio")
    app.setStyle("Fusion")
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
