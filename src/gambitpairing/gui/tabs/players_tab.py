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


import csv
import logging
from datetime import datetime
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal

from gambitpairing.gui.dialogs import PlayerManagementDialog
from gambitpairing.gui.notification import show_notification
from gambitpairing.gui.notournament_placeholder import (
    NoTournamentPlaceholder,
    PlayerPlaceholder,
)
from gambitpairing.player import Player


class NumericTableWidgetItem(QtWidgets.QTableWidgetItem):
    """Custom QTableWidgetItem for numerical sorting."""

    def __lt__(self, other):
        try:
            # Handle empty strings or non-numeric data gracefully
            self_val = float(self.text())
            other_val = float(other.text())
            return self_val < other_val
        except (ValueError, TypeError):
            # Fallback to string comparison if conversion fails
            return super().__lt__(other)


class PlayersTab(QtWidgets.QWidget):
    status_message = pyqtSignal(str)
    history_message = pyqtSignal(str)
    dirty = pyqtSignal()
    request_reset_tournament = pyqtSignal()
    standings_update_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tournament = None
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.player_group = QtWidgets.QGroupBox("Players")
        self.player_group.setToolTip("Manage players. Right-click a row for actions.")
        player_group_layout = QtWidgets.QVBoxLayout(self.player_group)

        # --- Player Table ---
        self.table_players = QtWidgets.QTableWidget()
        self.table_players.setToolTip(
            "Registered players. Right-click to Edit/Withdraw/Reactivate/Remove."
        )
        self.table_players.setColumnCount(4)  # Name, Rating, Age, Active
        self.table_players.setHorizontalHeaderLabels(
            ["Name", "Rating", "Age", "Status"]
        )
        self.table_players.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table_players.customContextMenuRequested.connect(
            self.on_player_context_menu
        )
        self.table_players.setAlternatingRowColors(True)
        self.table_players.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_players.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table_players.setSortingEnabled(True)

        # Resize columns
        header = self.table_players.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.table_players.setColumnWidth(1, 110)  # Rating
        self.table_players.setColumnWidth(2, 90)  # Age
        self.table_players.setColumnWidth(3, 130)  # Status

        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)
        header.setSectionsMovable(True)
        header.setHighlightSections(True)
        # Enable smooth sort arrow animation (Qt6+)
        try:
            header.setAnimated(True)
        except Exception:
            pass

        player_group_layout.addWidget(self.table_players)
        self.table_players.hide()  # Hide table initially

        self.btn_add_player_detail = QtWidgets.QPushButton(" Add New Player...")
        self.btn_add_player_detail.setToolTip(
            "Open dialog to add a new player with full details."
        )
        self.btn_add_player_detail.clicked.connect(self.add_player_detailed)
        player_group_layout.addWidget(self.btn_add_player_detail)
        self.main_layout.addWidget(self.player_group)

        # --- Compatibility: Legacy list_players for reset_tournament_state() ---
        self.list_players = QtWidgets.QListWidget()
        self.list_players.setVisible(False)  # Not used, but present for compatibility

        # Ensure sufficient row height for padded cells
        vheader = self.table_players.verticalHeader()
        vheader.setDefaultSectionSize(38)  # Increase default row height
        vheader.setMinimumSectionSize(38)

        # Initialize placeholders
        self.no_tournament_placeholder = NoTournamentPlaceholder(self, "Players")
        self.no_tournament_placeholder.create_tournament_requested.connect(
            self._trigger_create_tournament
        )
        self.no_tournament_placeholder.import_tournament_requested.connect(
            self._trigger_import_tournament
        )
        self.no_players_placeholder = PlayerPlaceholder(self)
        self.no_players_placeholder.import_players_requested.connect(
            self.import_players_csv
        )
        self.no_players_placeholder.add_player_requested.connect(
            self.add_player_detailed
        )

        # Hide placeholders initially
        self.no_tournament_placeholder.hide()
        self.no_players_placeholder.hide()
        self.main_layout.addWidget(self.no_tournament_placeholder)
        self.main_layout.addWidget(self.no_players_placeholder)

    def _calculate_age(self, dob_str: Optional[str]) -> Optional[int]:
        """Calculates age from a date of birth string (YYYY-MM-DD)."""
        if not dob_str:
            return None
        try:
            # Assuming dob_str is in a format that fromisoformat can handle, like YYYY-MM-DD
            dob_date = datetime.fromisoformat(
                dob_str.split(" ")[0]
            )  # Handle potential time part
            today = datetime.today()
            age = (
                today.year
                - dob_date.year
                - ((today.month, today.day) < (dob_date.month, dob_date.day))
            )
            return age
        except (ValueError, TypeError):
            return None  # Return None if format is wrong

    def on_player_context_menu(self, point: QtCore.QPoint) -> None:
        row = self.table_players.rowAt(point.y())
        if row < 0 or not self.tournament:
            return

        player_id_item = self.table_players.item(row, 0)
        if not player_id_item:
            return

        player_id = player_id_item.data(Qt.ItemDataRole.UserRole)
        player = self.tournament.players.get(player_id)
        if not player:
            return

        tournament_started = len(self.tournament.rounds_pairings_ids) > 0

        menu = QtWidgets.QMenu(self)
        edit_action = menu.addAction("Edit Player Details...")
        withdraw_action_text = (
            "Withdraw Player" if player.is_active else "Reactivate Player"
        )
        withdraw_action = menu.addAction(withdraw_action_text)
        remove_action = menu.addAction("Remove Player")

        edit_action.setEnabled(not tournament_started)
        remove_action.setEnabled(not tournament_started)
        withdraw_action.setEnabled(True)

        action = menu.exec(self.table_players.mapToGlobal(point))

        if action == edit_action:
            dialog = PlayerManagementDialog(
                self, player_data=player.to_dict(), tournament=self.tournament
            )
            if dialog.exec():
                data = dialog.get_player_data()
                if not data["name"]:
                    QtWidgets.QMessageBox.warning(
                        self, "Edit Error", "Player name cannot be empty."
                    )
                    return
                if data["name"] != player.name and any(
                    p.name == data["name"] for p in self.tournament.players.values()
                ):
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Edit Error",
                        f"Another player named '{data['name']}' already exists.",
                    )
                    return

                player.name = data["name"]
                player.rating = data["rating"]
                player.gender = data.get("gender")
                player.dob = data.get("dob")
                player.phone = data.get("phone")
                player.email = data.get("email")
                player.club = data.get("club")
                player.federation = data.get("federation")
                # Update FIDE data if provided
                if data.get("fide_id"):
                    player.fide_id = data.get("fide_id")
                    player.fide_title = data.get("fide_title")
                    player.fide_standard = data.get("fide_standard")
                    player.fide_rapid = data.get("fide_rapid")
                    player.fide_blitz = data.get("fide_blitz")
                    player.birth_year = data.get("birth_year")

                self.update_player_table_row(player)
                self.history_message.emit(f"Player '{player.name}' details updated.")
                self.dirty.emit()
        elif action == withdraw_action:
            player.is_active = not player.is_active
            status_log_msg = "Withdrawn" if not player.is_active else "Reactivated"
            self.update_player_table_row(player)
            self.history_message.emit(f"Player '{player.name}' {status_log_msg}.")
            self.dirty.emit()
            self.standings_update_requested.emit()
            self.update_ui_state()
        elif action == remove_action:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Remove Player",
                f"Remove player '{player.name}' permanently?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                if player.id in self.tournament.players:
                    del self.tournament.players[player.id]
                    self.history_message.emit(
                        f"Player '{player.name}' removed from tournament."
                    )
                self.table_players.removeRow(row)
                self.status_message.emit(f"Player '{player.name}' removed.")
        self.update_ui_state()

    def add_player_detailed(self):
        # This method's logic remains largely the same, but it will call add_player_to_table
        tournament_started = (
            self.tournament and len(self.tournament.rounds_pairings_ids) > 0
        )
        if tournament_started:
            QtWidgets.QMessageBox.warning(
                self,
                "Tournament Active",
                "Cannot add players after the tournament has started.",
            )
            return
        if not self.tournament:
            self.request_reset_tournament.emit()
            QtWidgets.QMessageBox.information(
                self,
                "New Tournament",
                "Please set up a new tournament before adding players.",
            )
            return

        dialog = PlayerManagementDialog(self, tournament=self.tournament)
        if dialog.exec():
            data = dialog.get_player_data()
            if not data["name"]:
                QtWidgets.QMessageBox.warning(
                    self, "Validation Error", "Player name cannot be empty."
                )
                return
            if any(p.name == data["name"] for p in self.tournament.players.values()):
                QtWidgets.QMessageBox.warning(
                    self, "Duplicate Player", f"Player '{data['name']}' already exists."
                )
                return
            new_player = Player(
                name=data["name"],
                rating=data["rating"],
                phone=data["phone"],
                email=data["email"],
                club=data["club"],
                federation=data["federation"],
                gender=data.get("gender"),
                dob=data.get("dob"),
                fide_id=data.get("fide_id"),
                fide_title=data.get("fide_title"),
                fide_standard=data.get("fide_standard"),
                fide_rapid=data.get("fide_rapid"),
                fide_blitz=data.get("fide_blitz"),
                birth_year=data.get("birth_year"),
            )
            self.tournament.players[new_player.id] = new_player
            self.add_player_to_table(new_player)
            self.status_message.emit(f"Added player: {new_player.name}")
            self.history_message.emit(
                f"Player '{new_player.name}' ({new_player.rating}) added."
            )
            self.dirty.emit()
            self.update_ui_state()

    def update_player_table_row(self, player: Player):
        """Finds and updates the QTableWidget row for a given player."""
        for i in range(self.table_players.rowCount()):
            item = self.table_players.item(i, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == player.id:
                # Update Name
                item.setText(player.name)

                # Update Rating
                rating_item = self.table_players.item(i, 1)
                rating_item.setText(str(player.rating or ""))

                # Update Age
                age_item = self.table_players.item(i, 2)
                age = self._calculate_age(player.dob)
                age_item.setText(str(age) if age is not None else "")

                # Update Status
                status_item = self.table_players.item(i, 3)
                status_text = "Active" if player.is_active else "Inactive"
                status_item.setText(status_text)

                # Update row color
                color = (
                    QtGui.QColor("gray")
                    if not player.is_active
                    else self.table_players.palette().color(
                        QtGui.QPalette.ColorRole.Text
                    )
                )
                item.setForeground(color)
                rating_item.setForeground(color)
                age_item.setForeground(color)
                status_item.setForeground(color)
                break

    def add_player_to_table(self, player: Player):
        self.table_players.setSortingEnabled(False)  # Disable sorting during insert
        row_position = self.table_players.rowCount()
        self.table_players.insertRow(row_position)

        # Name Item
        name_item = QtWidgets.QTableWidgetItem(player.name)
        name_item.setData(Qt.ItemDataRole.UserRole, player.id)

        # Rating Item
        rating_item = NumericTableWidgetItem(str(player.rating or ""))

        # Age Item
        age = self._calculate_age(player.dob)
        age_item = NumericTableWidgetItem(str(age) if age is not None else "")

        # Status Item
        status_text = "Active" if player.is_active else "Inactive"
        status_item = QtWidgets.QTableWidgetItem(status_text)

        # Set Tooltip
        tooltip_parts = [f"ID: {player.id}"]
        if player.gender:
            tooltip_parts.append(f"Gender: {player.gender}")
        if player.dob:
            tooltip_parts.append(f"Date of Birth: {player.dob}")
        if player.phone:
            tooltip_parts.append(f"Phone: {player.phone}")
        if player.email:
            tooltip_parts.append(f"Email: {player.email}")
        if player.club:
            tooltip_parts.append(f"Club: {player.club}")
        if player.federation:
            tooltip_parts.append(f"Federation: {player.federation}")
        # FIDE metadata if present
        if getattr(player, "fide_id", None):
            tooltip_parts.append(f"FIDE ID: {player.fide_id}")
        if getattr(player, "fide_title", None):
            tooltip_parts.append(f"Title: {player.fide_title}")
        if getattr(player, "fide_standard", None) is not None:
            tooltip_parts.append(f"Std: {player.fide_standard}")
        if getattr(player, "fide_rapid", None) is not None:
            tooltip_parts.append(f"Rapid: {player.fide_rapid}")
        if getattr(player, "fide_blitz", None) is not None:
            tooltip_parts.append(f"Blitz: {player.fide_blitz}")
        if getattr(player, "birth_year", None) is not None:
            tooltip_parts.append(f"Birth Year: {player.birth_year}")
        if getattr(player, "gender", None):
            tooltip_parts.append(f"Gender: {player.gender}")
        tooltip = "\n".join(tooltip_parts)
        name_item.setToolTip(tooltip)
        rating_item.setToolTip(tooltip)
        age_item.setToolTip(tooltip)
        status_item.setToolTip(tooltip)

        # Set color for inactive players
        if not player.is_active:
            color = QtGui.QColor("gray")
            name_item.setForeground(color)
            rating_item.setForeground(color)
            age_item.setForeground(color)
            status_item.setForeground(color)

        self.table_players.setItem(row_position, 0, name_item)
        self.table_players.setItem(row_position, 1, rating_item)
        self.table_players.setItem(row_position, 2, age_item)
        self.table_players.setItem(row_position, 3, status_item)

        self.table_players.setSortingEnabled(True)

    def import_players_csv(self):
        # This method's logic remains the same
        if self.tournament and len(self.tournament.rounds_pairings_ids) > 0:
            QtWidgets.QMessageBox.warning(
                self,
                "Import Error",
                "Cannot import players after tournament has started.",
            )
            return
        if not self.tournament:
            QtWidgets.QMessageBox.warning(
                self,
                "No Tournament",
                "Please create a tournament before importing players.",
            )
            return

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Players", "", "CSV Files (*.csv);;Text Files (*.txt)"
        )
        if not filename:
            return
        try:
            with open(
                filename, "r", encoding="utf-8-sig"
            ) as f:  # Use utf-8-sig for BOM
                reader = csv.DictReader(f)
                added_count = 0
                for row in reader:
                    name = row.get("Name")
                    if not name or any(
                        p.name == name for p in self.tournament.players.values()
                    ):
                        continue  # Skip empty names or duplicates
                    rating_str = row.get("Rating")
                    rating = (
                        int(rating_str) if rating_str and rating_str.isdigit() else None
                    )
                    player = Player(
                        name=name,
                        rating=rating,
                        gender=row.get("Gender"),
                        dob=row.get("Date of Birth"),
                        phone=row.get("Phone"),
                        email=row.get("Email"),
                        club=row.get("Club"),
                        federation=row.get("Federation"),
                    )
                    self.tournament.players[player.id] = player
                    added_count += 1
            if added_count > 0:
                self.history_message.emit(
                    f"Imported {added_count} players from {filename}."
                )
                self.dirty.emit()
                self.refresh_player_list()
                self.update_ui_state()
                # Modern notification
                try:
                    show_notification(
                        self,
                        f"Imported {added_count} players from {Path(filename).name}",
                        duration=3500,
                        notification_type="success",
                    )
                except Exception:
                    QtWidgets.QMessageBox.information(
                        self, "Import Successful", f"Imported {added_count} players."
                    )
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Import Notice",
                    "No new players were imported. Check for empty names or duplicates.",
                )
        except Exception as e:
            logging.exception("Error importing players:")
            try:
                show_notification(
                    self,
                    f"Error importing players: {e}",
                    duration=6000,
                    notification_type="error",
                )
            except Exception:
                QtWidgets.QMessageBox.critical(
                    self, "Import Error", f"Could not import players:\n{e}"
                )

    def export_players_csv(self):
        # This method's logic remains the same
        if not self.tournament or not self.tournament.players:
            QtWidgets.QMessageBox.information(
                self, "Export Error", "No players available to export."
            )
            return
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Players", "", "CSV Files (*.csv)"
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Name",
                        "Rating",
                        "Gender",
                        "Date of Birth",
                        "Phone",
                        "Email",
                        "Club",
                        "Federation",
                        "Active",
                        "ID",
                    ]
                )
                for player in sorted(
                    list(self.tournament.players.values()), key=lambda p: p.name
                ):
                    writer.writerow(
                        [
                            player.name,
                            player.rating if player.rating is not None else "",
                            player.gender or "",
                            player.dob or "",
                            player.phone or "",
                            player.email or "",
                            player.club or "",
                            player.federation or "",
                            "Yes" if player.is_active else "No",
                            player.id,
                        ]
                    )
            self.status_message.emit(f"Players exported to {filename}")
        except Exception as e:
            logging.exception("Error exporting players:")
            QtWidgets.QMessageBox.critical(
                self, "Export Error", f"Could not export players:\n{e}"
            )

    def set_tournament(self, tournament):
        self.tournament = tournament
        self.refresh_player_list()
        self._update_visibility()

    def _update_visibility(self):
        """Show/hide content based on tournament existence."""
        if not self.tournament:
            # No tournament: show only the placeholder
            self.no_tournament_placeholder.show()
            self.no_players_placeholder.hide()
            self.table_players.hide()
            self.btn_add_player_detail.hide()  # Completely hide the button
            self.player_group.hide()  # Hide the group box title for perfect wall
        else:
            # Tournament exists: hide placeholder and show appropriate content
            self.no_tournament_placeholder.hide()
            self.player_group.show()
            if not self.tournament.players:
                # Tournament but no players: show player placeholder
                self.no_players_placeholder.show()
                self.table_players.hide()
                self.btn_add_player_detail.hide()  # Hide until first player is added
                # Hide the group box frame/title to create seamless wall look
                self.player_group.hide()
            else:
                # Tournament with players: show table and add button
                self.no_players_placeholder.hide()
                self.player_group.show()
                self.table_players.show()
                self.btn_add_player_detail.show()
                tournament_started = len(self.tournament.rounds_pairings_ids) > 0
                self.btn_add_player_detail.setEnabled(not tournament_started)

    def update_ui_state(self):
        self._update_visibility()

    def refresh_player_list(self):
        self.table_players.setSortingEnabled(False)
        self.table_players.setRowCount(0)

        # Use the visibility method to handle all states
        self._update_visibility()

        # Only populate table if tournament exists and has players
        if self.tournament and self.tournament.players:
            for player in sorted(
                self.tournament.players.values(), key=lambda p: p.name
            ):
                self.add_player_to_table(player)
            self.table_players.setSortingEnabled(True)

    def _trigger_create_tournament(self):
        # Walk up the parent chain to find the main window
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "prompt_new_tournament"):
                parent.prompt_new_tournament()
                return
            parent = parent.parent()

    def _trigger_import_tournament(self):
        # Walk up the parent chain to find the main window
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "load_tournament"):
                parent.load_tournament()
                return
            parent = parent.parent()
