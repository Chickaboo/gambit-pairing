from typing import List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QFileInfo, Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import QMessageBox

from gambitpairing import APP_NAME, APP_VERSION, utils
from gambitpairing.gui.dialogs import (
    PlayerManagementDialog,
)
from gambitpairing.gui.notification import show_notification
from gambitpairing.tournament import Tournament
from gambitpairing.utils import setup_logger

logger = setup_logger(__name__)


class ImportPlayer:
    """Help import players into a chess tournament."""

    def __init__(self, main_window) -> None:
        """Initilize an import players class. Is utilized to import players."""
        logger.info("%s initialized with main_window: %s", self, main_window)
        self.main_window = main_window

    def import_players_from_api(self) -> None:
        """Import players into a tournament for chess a federation API."""
        breakpoint()
        if not self.main_window.tournament:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "No Tournament",
                "Please create a tournament before importing players.",
            )
            return
        if len(self.main_window.tournament.rounds_pairings_ids) > 0:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Tournament Active",
                "Cannot import players after the tournament has started.",
            )
            return

        dialog = PlayerManagementDialog(
            parent=self.main_window, tournament=self.main_window.tournament
        )
        dialog.tab_widget.setCurrentIndex(1)  # Switch to FIDE tab
        if dialog.exec():
            # Player was added through the integrated dialog
            self.main_window.players_tab.refresh_player_list()
            self.main_window.players_tab.update_ui_state()
            self.main_window.mark_dirty()
            # Provide modern notification feedback
            try:
                show_notification(
                    self.main_window,
                    "Players imported via API.",
                    duration=3000,
                    notification_type="success",
                )
            except Exception:
                pass


#  LocalWords:  GambitPairingMainWindow
