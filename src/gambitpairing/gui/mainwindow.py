"""Main GUI window for Gambit Pairing."""

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


import json
import logging
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QFileInfo, Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import QFormLayout, QLayout, QMessageBox, QWidget

from gambitpairing import APP_NAME, APP_VERSION, utils
from gambitpairing.gui.dialogs import (
    AboutDialog,
    NewTournamentDialog,
    SettingsDialog,
    UpdateDownloadDialog,
    UpdatePromptDialog,
)
from gambitpairing.gui.import_player import ImportPlayer
from gambitpairing.gui.tabs import (
    CrosstableTab,
    HistoryTab,
    PlayersTab,
    StandingsTab,
    TournamentTab,
)
from gambitpairing.player import Player
from gambitpairing.tournament import Tournament
from gambitpairing.update import Updater, UpdateWorker
from gambitpairing.utils import is_round_robin, setup_logger

logger = setup_logger(__name__)


# --- Main Application Window ---
class GambitPairingMainWindow(QtWidgets.QMainWindow):
    """Main application window for Gambit Pairing."""

    def __init__(self) -> None:
        super().__init__()
        self.tournament: Optional[Tournament] = None
        # current_round_index tracks rounds with recorded results.
        # 0 = no results yet. 1 = R1 results are in.
        self.current_round_index: int = 0
        self.last_recorded_results_data: List[Tuple[str, str, float]] = []
        self._current_filepath: Optional[str] = None
        self._dirty: bool = False
        self.is_updating = False
        self.updater: Optional[Updater] = Updater(APP_VERSION)
        # import player is a class containing import player logic
        self.import_mgr = ImportPlayer(self)

        self._setup_ui()
        self._update_ui_state()

        # Check for pending update first, then check for new online updates.
        if not self.check_for_pending_update():
            if self.updater:
                QtCore.QTimer.singleShot(1500, self.check_for_updates_auto)

    def _setup_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 1000, 800)
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QtWidgets.QVBoxLayout(self.central_widget)
        self._setup_main_panel()
        self._setup_menu()
        self._setup_toolbar()
        self.statusBar().showMessage("Ready - Create New or Load Tournament.")
        logging.info(f"{APP_NAME} v{APP_VERSION} started.")

    def _setup_main_panel(self) -> None:
        """Create the tab widget and populates it with the modular tab classes."""
        self.tabs = QtWidgets.QTabWidget()
        self.main_layout.addWidget(self.tabs)

        self.players_tab = PlayersTab(self)
        self.tournament_tab = TournamentTab(self)
        self.standings_tab = StandingsTab(self)
        self.crosstable_tab = CrosstableTab(self)
        self.history_tab = HistoryTab(self)

        self.players_tab.status_message.connect(self.statusBar().showMessage)
        self.tournament_tab.status_message.connect(self.statusBar().showMessage)
        self.players_tab.history_message.connect(self.history_tab.update_history_log)
        self.tournament_tab.history_message.connect(self.history_tab.update_history_log)
        self.players_tab.dirty.connect(self.mark_dirty)
        self.tournament_tab.dirty.connect(self.mark_dirty)
        self.tournament_tab.dirty.connect(self._update_ui_state)
        self.tournament_tab.round_completed.connect(self._on_round_completed)
        self.tournament_tab.standings_update_requested.connect(
            self.standings_tab.update_standings_table
        )
        self.tournament_tab.standings_update_requested.connect(
            self.players_tab.refresh_player_list
        )

        self.tabs.addTab(self.players_tab, "Players")
        self.tabs.addTab(self.tournament_tab, "Tournament")
        self.tabs.addTab(self.standings_tab, "Standings")
        self.tabs.addTab(self.crosstable_tab, "Cross-Table")
        self.tabs.addTab(self.history_tab, "History Log")

    def _setup_menu(self) -> None:
        """Set up the main menu bar, connecting actions to methods in the main window or tabs."""
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")
        self.new_action = self._create_action(
            "&New Tournament...", self.prompt_new_tournament, "Ctrl+N"
        )
        self.load_action = self._create_action(
            "&Load Tournament...", self.load_tournament, "Ctrl+O"
        )
        self.save_action = self._create_action(
            "&Save Tournament", self.save_tournament, "Ctrl+S"
        )
        self.save_as_action = self._create_action(
            "Save Tournament &As...",
            lambda: self.save_tournament(save_as=True),
            "Ctrl+Shift+S",
        )
        self.export_standings_action = self._create_action(
            "&Export Standings...", self.standings_tab.export_standings
        )
        self.settings_action = self._create_action(
            "S&ettings...", self.show_tournament_settings_dialog
        )
        self.exit_action = self._create_action("E&xit", self.close, "Ctrl+Q")

        file_menu.addActions(
            [self.new_action, self.load_action, self.save_action, self.save_as_action]
        )
        file_menu.addSeparator()
        file_menu.addActions(
            [
                self.export_standings_action,
            ]
        )
        file_menu.addSeparator()
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        # Tournament Menu
        tournament_menu = menu_bar.addMenu("&Tournament")
        self.start_action = self._create_action(
            "&Start Tournament", self.tournament_tab.start_tournament
        )
        self.prepare_round_action = self._create_action(
            "&Prepare Next Round", self.tournament_tab.prepare_next_round
        )
        self.record_results_action = self._create_action(
            "&Record Results && Advance", self.tournament_tab.record_and_advance
        )
        self.undo_results_action = self._create_action(
            "&Undo Last Results", self.tournament_tab.undo_last_results
        )
        tournament_menu.addActions(
            [
                self.start_action,
                self.prepare_round_action,
                self.record_results_action,
                self.undo_results_action,
            ]
        )

        # Player Menu
        player_menu = menu_bar.addMenu("&Players")
        self.add_player_action = self._create_action(
            "&Add Player...", self.players_tab.add_player_detailed
        )
        player_menu.addAction(self.add_player_action)
        self.import_players_action = self._create_action(
            "&Import Players from CSV...", self.players_tab.import_players_csv
        )
        self.export_players_action = self._create_action(
            "&Export Players to CSV...", self.players_tab.export_players_csv
        )
        player_menu.addSeparator()
        player_menu.addActions(
            [
                self.import_players_action,
                self.export_players_action,
            ]
        )

        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction("About...", self.show_about_dialog)
        self.update_action = self._create_action(
            "Check for &Updates...", self.check_for_updates_manual
        )
        help_menu.addAction(self.update_action)

    def _create_action(
        self, text: str, slot: Callable, shortcut: str = "", tooltip: str = ""
    ) -> QAction:
        """Create and configure a QAction.

        Parameters
        ----------
            text: The text to display for the action.
            slot: The function to call when the action is triggered.
            shortcut: Optional keyboard shortcut (e.g., "Ctrl+N").
            tooltip: Optional tooltip to show on hover.

        Returns
        -------
            The configured QAction.
        """
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if tooltip:
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
        action.setIconVisibleInMenu(False)  # Hide icon in menus
        return action

    def _setup_toolbar(self) -> None:
        """Set up the main application toolbar.

        Icons are loaded from the system theme for a native look and feel.
        """
        toolbar = self.addToolBar("Main Toolbar")
        assert toolbar is not None
        # Prevent detaching / floating
        toolbar.setMovable(False)
        try:
            toolbar.setFloatable(False)
        except Exception:
            pass
        toolbar.setAllowedAreas(
            Qt.ToolBarArea.TopToolBarArea | Qt.ToolBarArea.BottomToolBarArea
        )  # restrict just in case
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        toolbar.setIconSize(QtCore.QSize(24, 24))
        toolbar.setStyleSheet(
            """
            QToolBar {
                background: #f9fafb;
                border-bottom: 1px solid #bbb;
            }
        """
        )
        QtGui.QIcon.setThemeName(
            "Adwaita"
        )  # Adwaita is often monochrome, fallback to system if not found
        self.new_action.setIcon(QtGui.QIcon.fromTheme("document-new"))
        self.load_action.setIcon(QtGui.QIcon.fromTheme("document-open"))
        self.save_action.setIcon(QtGui.QIcon.fromTheme("document-save"))
        self.start_action.setIcon(QtGui.QIcon.fromTheme("media-playback-start"))
        self.prepare_round_action.setIcon(QtGui.QIcon.fromTheme("view-refresh"))
        self.record_results_action.setIcon(QtGui.QIcon.fromTheme("document-send"))
        self.undo_results_action.setIcon(QtGui.QIcon.fromTheme("edit-undo"))
        # Add toolbar actions
        toolbar.addActions([self.new_action, self.load_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addActions(
            [
                self.start_action,
                self.prepare_round_action,
                self.record_results_action,
                self.undo_results_action,
            ]
        )

    def _update_ui_state(self) -> None:
        """Update the state of UI elements based on the tournament's current state."""
        tournament_exists = self.tournament is not None
        pairings_generated = (
            len(self.tournament.rounds_pairings_ids) if tournament_exists else 0
        )
        results_recorded = self.current_round_index
        total_rounds = self.tournament.num_rounds if tournament_exists else 0
        tournament_started = tournament_exists and pairings_generated > 0
        tournament_finished = (
            tournament_exists and results_recorded >= total_rounds and total_rounds > 0
        )

        # can_start = tournament_exists and not tournament_started and len(self.tournament.players) >= 2
        can_start = tournament_exists and not tournament_started
        can_prepare = (
            tournament_exists
            and tournament_started
            and pairings_generated == results_recorded
            and not tournament_finished
        )
        can_record = (
            tournament_exists
            and tournament_started
            and pairings_generated > results_recorded
            and not tournament_finished
        )
        can_undo = (
            tournament_exists
            and results_recorded > 0
            and bool(self.last_recorded_results_data)
        )

        # Update main actions (toolbar and menu)
        self.start_action.setEnabled(can_start)
        self.prepare_round_action.setEnabled(can_prepare)
        self.record_results_action.setEnabled(can_record)
        self.undo_results_action.setEnabled(can_undo)
        self.save_action.setEnabled(tournament_exists)
        self.save_as_action.setEnabled(tournament_exists)
        self.export_standings_action.setEnabled(
            tournament_exists and results_recorded > 0
        )
        self.import_players_action.setEnabled(
            tournament_exists and not tournament_started
        )
        self.export_players_action.setEnabled(
            tournament_exists and len(self.tournament.players) > 0
        )
        self.add_player_action.setEnabled(not tournament_started)
        self.settings_action.setEnabled(tournament_exists)

        # Do NOT disable the Players tab after tournament starts
        # self.tabs.setTabEnabled(self.tabs.indexOf(self.players_tab), not tournament_started)

        # Delegate UI state updates to the tabs themselves
        self.players_tab.update_ui_state()
        self.tournament_tab.update_ui_state()
        self.standings_tab.update_ui_state()
        self.crosstable_tab.update_ui_state()
        self.history_tab.update_ui_state()

        # Update window title
        title = APP_NAME
        if self.tournament:
            base_name = self.tournament.name
            if self._dirty:
                base_name += "*"

            if self._current_filepath:
                file_name = QFileInfo(self._current_filepath).fileName()
                title = f"{base_name} - {file_name} - {APP_NAME}"
            else:
                title = f"{base_name} - {APP_NAME}"
        else:
            if self._current_filepath:
                title = f"{QFileInfo(self._current_filepath).fileName()} - {APP_NAME}"

        self.setWindowTitle(title)

        # Update status bar
        status = "Ready"
        if tournament_exists:
            if not tournament_started:
                status = f"Tournament '{self.tournament.name}': Add players, then Start. {len(self.tournament.players)} players registered."
            elif can_record:
                status = f"Round {results_recorded + 1} pairings ready for '{self.tournament.name}'. Please enter results."
            elif can_prepare:
                status = f"Round {results_recorded} results recorded for '{self.tournament.name}'. Prepare Round {results_recorded + 1}."
            elif tournament_finished:
                status = f"Tournament '{self.tournament.name}' finished. Final standings are available."
            else:
                status = f"Tournament '{self.tournament.name}' in progress. Completed rounds: {results_recorded}/{total_rounds}."
        else:
            status = "Ready - Create New or Load Tournament."
        self.statusBar().showMessage(status)

    def mark_dirty(self, dirty=True) -> None:
        """Mark as dirty."""
        if self._dirty != dirty:
            self._dirty = dirty
            self._update_ui_state()

    def mark_clean(self) -> None:
        """Mark as clean."""
        self.mark_dirty(False)

    def _set_tournament_on_tabs(self) -> None:
        """Pass the current tournament object to all tabs so they can access its data."""
        for tab in [
            self.players_tab,
            self.tournament_tab,
            self.standings_tab,
            self.crosstable_tab,
            self.history_tab,
        ]:
            if hasattr(tab, "set_tournament"):
                tab.set_tournament(self.tournament)
        # Also set current_round_index on tournament_tab if method exists
        if hasattr(self.tournament_tab, "set_current_round_index"):
            self.tournament_tab.set_current_round_index(self.current_round_index)
        # Ensure UI state is updated after tournament propagation
        self._update_ui_state()

    def reset_tournament_state(self) -> None:
        """Reset the entire application to a clean state."""
        self.tournament = None
        self.current_round_index = 0
        self.last_recorded_results_data = []
        self._current_filepath = None
        self.mark_clean()

        self._set_tournament_on_tabs()  # Pass None to clear tabs

        # Explicitly clear UI elements in tabs
        self.players_tab.clean()
        self.tournament_tab.table_pairings.setRowCount(0)
        self.tournament_tab.lbl_bye.setText("Bye: None")
        self.standings_tab.table_standings.setRowCount(0)
        self.crosstable_tab.table_crosstable.setRowCount(0)
        self.history_tab.history_view.clear()

        self._update_ui_state()

    def prompt_new_tournament(self) -> None:
        """Show the new tournament prompt."""
        if not self.check_save_if_dirty():
            logger.info("save cancelled")
            return

        new_tour_dlg = NewTournamentDialog(self)
        if new_tour_dlg.exec():
            data = new_tour_dlg.get_data()
            if data:
                name, num_rounds, tiebreak_order, pairing_system = data
                self.reset_tournament_state()
                self.tournament = Tournament(
                    name=name,
                    players=[],
                    num_rounds=num_rounds,
                    tiebreak_order=tiebreak_order,
                    pairing_system=pairing_system,
                )
                # Store pairing_system as an attribute if needed:
                self.pairing_system = pairing_system

                log_msg = f"--- New Tournament '{name}' Created (Rounds: {num_rounds}, Pairing: {pairing_system}) ---"
                self.update_history_log(log_msg)
                logger.info(log_msg)

                self.mark_dirty()
                self._set_tournament_on_tabs()
                self.standings_tab.update_standings_table_headers()
                self._update_ui_state()

    def show_tournament_settings_dialog(self) -> bool:
        """Show the tournament settings dialog."""
        if not self.tournament:
            logger.info("No tournament, no settings")
            return False

        dialog = SettingsDialog(
            self.tournament.num_rounds, self.tournament.tiebreak_order, self
        )
        tournament_started = len(self.tournament.rounds_pairings_ids) > 0
        if is_round_robin(self.tournament):
            # Hide rounds spinbox if round robin
            dialog.spin_num_rounds.hide()
            # Find and hide the label too - look through the form layout
            rounds_group = None

            dia_layout: Optional[QLayout] = dialog.layout()

            assert dia_layout  # ensure layout

            for i in range(dia_layout.count()):
                item = dia_layout.itemAt(i)
                widget: QWidget | None = dia_layout.widget()
                assert widget  # ensure

                if item and widget and isinstance(widget, QtWidgets.QGroupBox):
                    if widget.title() == "General":
                        rounds_group = item.widget()
                        break

            if rounds_group and isinstance(
                rounds_group.layout(), QtWidgets.QFormLayout
            ):
                form_layout: QFormLayout = rounds_group.layout()  # type: ignore[assignment]
                label = form_layout.labelForField(dialog.spin_num_rounds)
                if label:
                    label.hide()

            dialog.spin_num_rounds.setToolTip(
                "Number of rounds is fixed for Round Robin: players - 1."
            )
        else:
            dialog.spin_num_rounds.setEnabled(not tournament_started)
            dialog.spin_num_rounds.setToolTip("")

        if dialog.exec():
            new_rounds, new_tiebreaks = dialog.get_settings()
            if (
                self.tournament.num_rounds != new_rounds
                and not tournament_started
                and getattr(self.tournament, "pairing_system", None) != "round_robin"
            ):
                self.tournament.num_rounds = new_rounds
                self.update_history_log(f"Number of rounds set to {new_rounds}.")
                self.mark_dirty()

            if self.tournament.tiebreak_order != new_tiebreaks:
                self.tournament.tiebreak_order = new_tiebreaks
                self.update_history_log("Tiebreak order updated.")
                self.mark_dirty()
                self.standings_tab.update_standings_table_headers()
                self.standings_tab.update_standings_table()

            self._update_ui_state()
            return True
        return False

    def update_history_log(self, message: str) -> None:
        """Append a timestamped message to the history log tab."""
        self.history_tab.update_history_log(message)

    def save_tournament(self, save_as=False) -> bool:
        """Save the current tournament.

        Returns
        -------
        bool
            If it was successful
        """
        if not self.tournament:
            return False
        if not self._current_filepath or save_as:
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save Tournament", "", "JSON Files (*.json)"
            )
            if not filename:
                return False
            self._current_filepath = filename
            logger.info("filepath set to %s", filename)

        try:
            data = self.tournament.to_dict()
            data["gui_state"] = {
                "current_round_index": self.current_round_index,
                "last_recorded_results_data": self.last_recorded_results_data,
            }
            # check to see if file exists, and confirm prior to overwrite
            if Path(self._current_filepath).exists():
                # confirm before over write
                if not self.get_confirmation(
                    action="will overwrite tournament", message="Is that what you want?"
                ):
                    return False
                # else continue

            with open(self._current_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.mark_clean()
            self.statusBar().showMessage(  # type: ignore[union-attr]
                f"Tournament saved to {self._current_filepath}"
            )

            log_msg = f"--- Tournament saved to {QFileInfo(self._current_filepath).fileName()} ---"
            self.update_history_log(log_msg)
            logger.info(log_msg)
            return True
        except Exception as e:
            logging.exception("Error saving tournament:")
            QtWidgets.QMessageBox.critical(
                self, "Save Error", f"Could not save tournament:\n{e}"
            )
            return False

    def load_tournament(self) -> None:
        """Load a tournament from a JSON file."""
        if not self.check_save_if_dirty():
            return
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Tournament", "", "JSON Files (*.json)"
        )
        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.reset_tournament_state()
            self.tournament = Tournament.from_dict(data)

            gui_state = data.get("gui_state", {})
            self.current_round_index = gui_state.get("current_round_index", 0)
            self.last_recorded_results_data = gui_state.get(
                "last_recorded_results_data", []
            )
            self._current_filepath = filename

            self._set_tournament_on_tabs()

            # Refresh all views
            self.players_tab.refresh_player_list()
            self.standings_tab.update_standings_table_headers()
            self.standings_tab.update_standings_table()
            self.crosstable_tab.update_crosstable()

            # Display pairings for the current round if they exist
            if self.tournament and 0 <= self.current_round_index < len(
                self.tournament.rounds_pairings_ids
            ):
                pairings, bye_player = self.tournament.get_pairings_for_round(
                    self.current_round_index
                )
                self.tournament_tab.display_pairings_for_input(
                    pairings, [bye_player] if bye_player else []
                )
            else:
                self.tournament_tab.clear_pairings_display()

            self.mark_clean()
            self.update_history_log(
                f"--- Tournament loaded from {QFileInfo(filename).fileName()} ---"
            )
            self.statusBar().showMessage(f"Loaded tournament: {self.tournament.name}")

        except Exception as e:
            logging.exception("Error loading tournament:")
            self.reset_tournament_state()
            QtWidgets.QMessageBox.critical(
                self, "Load Error", f"Could not load tournament file:\n{e}"
            )

        self._update_ui_state()

    def check_save_if_dirty(self) -> bool:
        """Check if you want to save if the self is dirty.

        Returns
        -------
        bool
            good to proceed
        """
        if not self._dirty:
            return True

        msgbox = QtWidgets.QMessageBox(self)
        msgbox.setWindowTitle("Unsaved Changes")
        msgbox.setText("You have unsaved changes. Do you want to save them?")
        msgbox.setIcon(QtWidgets.QMessageBox.Icon.Warning)

        # Create custom buttons
        btn_save = QtWidgets.QPushButton("Save")
        btn_discard = QtWidgets.QPushButton("Close without Saving")
        btn_cancel = QtWidgets.QPushButton("Cancel")

        # Add buttons to msgbox
        msgbox.addButton(btn_save, QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        msgbox.addButton(btn_discard, QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        msgbox.addButton(btn_cancel, QtWidgets.QMessageBox.ButtonRole.RejectRole)

        # I do not know enough about pyQT but in line does not seem ideal
        msgbox.setStyleSheet(
            """
            QPushButton {
                padding: 6px 14px;
                font-size: 10pt;
                min-width: 140px;
            }
        """
        )

        msgbox.exec()
        clicked = msgbox.clickedButton()

        if clicked == btn_save:
            return self.save_tournament()
        elif clicked == btn_discard:
            return True
        else:
            return False

    def show_about_dialog(self) -> None:
        """Show the About dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    def check_for_pending_update(self) -> bool:
        """Check for a previously downloaded update and asks to install it."""
        if not self.updater:
            return False
        pending_path = self.updater.get_pending_update_path()
        if pending_path:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Update Ready to Install",
                "A downloaded update is ready. This will restart the application.\n\nInstall now?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
            )

            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.is_updating = True
                status_br = self.statusBar()
                assert status_br
                status_br.showMessage("Restarting to apply update...")
                self.updater.apply_update(pending_path)
                QtCore.QTimer.singleShot(100, self.close)
                return True  # Update is being applied
            else:
                # User chose not to install. Let's ask if they want to discard it.
                discard_reply = QtWidgets.QMessageBox.question(
                    self,
                    "Discard Update?",
                    "Do you want to discard the downloaded update? If not, you will be asked again on the next launch.",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                )
                if discard_reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    self.updater.cleanup_pending_update()
        return False

    def check_for_updates_manual(self) -> None:
        """Manually checks for updates and notifies the user of the result."""
        if not getattr(sys, "frozen", False):
            QtWidgets.QMessageBox.information(
                self,
                "Update Check",
                "Automatic updates are only available in packaged releases.\n\n"
                "If you installed from source, please update using git or your package manager. ie: `pip install --upgrade [git-root]`",
            )
            return
        if not self.updater:
            QtWidgets.QMessageBox.information(
                self, "Update Check", "The update checker is not configured."
            )
            return
        stus_br = self.statusBar()
        assert stus_br
        stus_br.showMessage("Checking for updates...")
        has_update = self.updater.check_for_updates()
        if has_update:
            self.prompt_update()
        else:
            stus_br.showMessage("No new updates available.")
            QtWidgets.QMessageBox.information(
                self,
                "Update Check",
                f"You are using the latest version of {APP_NAME} ({APP_VERSION}).",
            )

    def check_for_updates_auto(self) -> None:
        """Automatically checks for updates in the background."""
        if not getattr(sys, "frozen", False):
            return
        if not self.updater:
            return
        if self.updater.check_for_updates():
            self.prompt_update()

    def prompt_update(self) -> None:
        """Show a modern dialog prompting the user to download the new version."""
        if not self.updater or not self.updater.latest_version_info:
            return

        latest_version = self.updater.get_latest_version()
        release_notes = self.updater.get_release_notes()

        if not all([latest_version, release_notes]):
            QtWidgets.QMessageBox.warning(
                self, "Update Error", "Could not retrieve complete update information."
            )
            return

        dialog = UpdatePromptDialog(
            new_version=latest_version,
            current_version=APP_VERSION,
            release_notes=release_notes,
            parent=self,
        )

        if dialog.exec():
            self.start_update_download()

    def start_update_download(self) -> None:
        """Initiate the update download and shows the progress dialog."""
        if not self.updater:
            return

        self.statusBar().showMessage("Starting update download...")
        self.download_dialog = UpdateDownloadDialog(self)

        self.thread = QtCore.QThread()
        self.worker = UpdateWorker(self.updater)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.download_dialog.update_progress)
        self.worker.status.connect(self.download_dialog.update_status)
        self.worker.done.connect(self.on_update_done)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.error.connect(self.thread.quit)
        self.worker.error.connect(self.worker.deleteLater)

        self.thread.start()
        self.download_dialog.exec()

    def on_update_done(self, success: bool, message: str) -> None:
        """Handle both success and error for update in a modern dialog."""
        if success:
            self.download_dialog.show_complete()
            # Connect restart button to restart logic
            self.download_dialog.restart_btn.clicked.disconnect()
            self.download_dialog.restart_btn.clicked.connect(
                lambda: self._restart_with_update(message)
            )
        else:
            self.download_dialog.show_error(message)
            self.download_dialog.close_btn.clicked.disconnect()
            self.download_dialog.close_btn.clicked.connect(self.download_dialog.close)

    def _restart_with_update(self, extracted_path: str) -> None:
        self.is_updating = True
        self.statusBar().showMessage("Restarting to apply update...")  # type: ignore[union-attr]
        self.updater.apply_update(extracted_path)  # type: ignore[union-attr]
        QtCore.QTimer.singleShot(100, self.close)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Close event handling."""
        if event == None:
            return

        if self.is_updating:
            event.accept()
            return

        if self.check_save_if_dirty():
            logging.info(f"{APP_NAME} closing.")
            event.accept()
        else:
            event.ignore()

    def _on_round_completed(self, round_index: int) -> None:
        """Slot called when a round is recorded and the tournament is advanced."""
        self.current_round_index = round_index
        self.mark_dirty()
        self._update_ui_state()

    def set_app_instance(self, app) -> None:
        """Store a reference to the QApplication instance for stylesheet control."""
        self._app_instance = app

    def restart_application(self) -> None:
        """Restart the application cleanly."""
        utils.restart_application()

    def get_confirmation(
        self, action="", message="Are you sure you want to proceed?"
    ) -> bool:
        """Get confirmation from the user."""
        reply = QMessageBox.question(
            self,
            action,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "Success", "Action completed!")
            return True
        return False


#  LocalWords:  bbb px ettings
