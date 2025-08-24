"""Logging utilities."""

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


import logging
import os
import sys

from PyQt6 import QtCore

# the logger format used
LOG_FMT = "LVL: %(levelname)s | FILE PATH: %(pathname)s | FUN: %(funcName)s | msg: %(message)s | ln#:%(lineno)d"


# --- Logging Setup ---
def setup_logger(logger_name: str) -> logging.Logger:
    """Set up loger for a python module.

    Sets up file handler and console handler

    Parameters
    ----------
    logger_name : str
        The name for the logger, __name__ is idiomatic

    Returns
    -------
    logging.Logger
        the created logger
    """
    # Setup logging to file and console
    lgr = logging.getLogger(name=logger_name)
    lgr.setLevel(logging.INFO)  # Set minimum level
    # Remove any existing handlers on this logger to avoid duplicates
    for _h in list(lgr.handlers):
        lgr.removeHandler(_h)
    # formatter
    log_formatter = logging.Formatter(LOG_FMT)
    # File Handler
    # Use a dedicated "Gambit Pairing" folder in roaming AppData on Windows.
    # Otherwise fall back to Qt's AppDataLocation or the temp location.
    file_handler = None
    try:
        # Preferred Windows location: %APPDATA%\Gambit Pairing
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA")
            if appdata:
                log_folder = os.path.join(appdata, "Gambit Pairing")
            else:
                # Fallback to Qt location if APPDATA isn't set for some reason
                log_folder = QtCore.QStandardPaths.writableLocation(
                    QtCore.QStandardPaths.StandardLocation.AppDataLocation
                )
        else:
            # Non-Windows: prefer Qt's AppDataLocation then TempLocation
            log_folder = QtCore.QStandardPaths.writableLocation(
                QtCore.QStandardPaths.StandardLocation.AppDataLocation
            )
            if not log_folder:
                log_folder = QtCore.QStandardPaths.writableLocation(
                    QtCore.QStandardPaths.StandardLocation.TempLocation
                )

        if log_folder:
            # use a "logs" sub folder
            log_folder = os.path.join(log_folder, "logs")
            # Ensure the directory exists
            try:
                os.makedirs(log_folder, exist_ok=True)
            except Exception:
                # If we can't create the folder, fall back to temp dir
                log_folder = QtCore.QStandardPaths.writableLocation(
                    QtCore.QStandardPaths.StandardLocation.TempLocation
                )
                log_folder = os.path.join(log_folder, "logs")
                os.makedirs(log_folder, exist_ok=True)

            log_path = os.path.join(log_folder, "gambit-pairing.log")
            # Use RotatingFileHandler to prevent unbounded log growth
            try:
                file_handler = RotatingFileHandler(
                    log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
                )
                file_handler.setFormatter(log_formatter)
                print(f"Logging to: {log_path}")  # Inform user where logs are
            except Exception:
                file_handler = None
        else:
            print("Warning: Could not determine writable location for log file.")
            file_handler = None
    except Exception:
        # If anything goes wrong creating the file handler, continue without file logging
        file_handler = None

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)
    # add handlers
    lgr.addHandler(console_handler)
    if file_handler:
        lgr.addHandler(file_handler)
    lgr.debug("logger %s initialized", logger_name)
    return lgr


#  LocalWords:  QListWidget
