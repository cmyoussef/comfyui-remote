"""GUI launcher."""
import sys
from PyQt5 import QtWidgets
from ..ui.qt.views.main_window import MainWindow


class GuiCommand:
    def build_parser(self, sub):
        p = sub.add_parser("gui", help="Launch GUI")
        p.set_defaults(func=self.run)

    def run(self, _args):
        app = QtWidgets.QApplication(sys.argv)
        win = MainWindow()
        win.show()
        sys.exit(app.exec_())
