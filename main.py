# main.py

import sys
from PyQt6.QtWidgets import QApplication
from gui import MagneticGUI


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MagneticGUI()
    window.show()
    sys.exit(app.exec())