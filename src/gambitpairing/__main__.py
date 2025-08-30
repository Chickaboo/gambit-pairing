"""Gambit Pairing entry point."""

# Gambit Pairing
# Copyright (C) 2025  Gambit Pairing developers
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import platform
import sys
from pathlib import Path

from importlib_resources import files
from PyQt6 import QtWidgets
from PyQt6.QtCore import QDir
from PyQt6.QtGui import QIcon

from gambitpairing.exceptions import IconException, StyleException
from gambitpairing.gui.mainwindow import GambitPairingMainWindow
from gambitpairing.resources.resource_utils import (
    get_resource_path,
    read_resource_text,
)
from gambitpairing.utils import setup_logger

logger = setup_logger(__name__)


def main():
    """Entry point."""
    # define aliases used in styles.qss
    icon_path = str(Path(str(files("gambitpairing.resources.icons"))))
    # set the qt search path for use in styles.qss
    QDir.setSearchPaths("icons", [icon_path])
    exit_code = run_app()
    logger.info("run_app() exited with code: %s", exit_code)
    sys.exit(exit_code)


def set_application_icon(app: QtWidgets.QApplication) -> None:
    """Set the application icon.

    Parameters
    ----------
    app : QtWidgets.QApplication
       The app to set the icon for

    Returns
    -------
    None

    Raises
    ------
    IconException
        When icon is not a QIcon
    """
    icon_path = get_resource_path("icon.png", subpackage="icons")

    logger.info("icon_path: (%s)\n", icon_path)
    icon = QIcon(str(icon_path))

    if icon and isinstance(icon, QIcon):
        app.setWindowIcon(icon)
        logger.info("Successfully set application icon")
    else:
        raise IconException("icon not a QIcon, icon instance of type(%s)", type(icon))


def set_application_style(app: QtWidgets.QApplication) -> None:
    """Set the application style.

    Parameters
    ----------
    app : QtWidgets.QApplication
       The app to set the style for

    Returns
    -------
    None

    Raises
    ------
    StyleException
        When style fails to be set
    """
    # to ensure it is bound, or mypy bitches
    style_text = ""
    try:
        style_text = read_resource_text("styles.qss")

        logger.debug("style_text: (%s)\n", style_text)
        #  apply style sheet
        app.setStyleSheet(style_text)
        logger.debug("set style sheet to:\n%s", style_text)

    except Exception as e:
        raise StyleException(
            "Exception (%s)\n raised when setting app style. style_text: \n %s",
            e,
            style_text,
        )


def run_app() -> int:
    """Run the gui application.

    Returns
    -------
    int
        the exit code from app.exec()

    Raises
    ------
    IconException
        When icon is not a QIcon
    """
    app = QtWidgets.QApplication(sys.argv)

    # Set cross-platform application icon
    set_application_icon(app)
    # Get current platform
    system = platform.system()

    if system == "Windows":
        app.setStyle("WindowsVista")  # windows
    elif system == "Darwin":  # macOS
        app.setStyle("macos")
    else:
        app.setStyle("fusion")  # Best cross-platform option

    # set app style
    set_application_style(app)

    window = GambitPairingMainWindow()
    window.set_app_instance(app)
    window.show()

    exit_code = app.exec()
    return exit_code


if __name__ == "__main__":
    main()

#  LocalWords:  IconException QIcon WindowsVista macos StyleException
