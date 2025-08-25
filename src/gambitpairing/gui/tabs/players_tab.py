"""Players tab in the GUI."""

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
from gambitpairing.gui.notournament_placeholder import (
    NoTournamentPlaceholder,
    PlayerPlaceholder,
)
from gambitpairing.player import Player


class NumericTableWidgetItem(QtWidgets.QTableWidgetItem):
    """Custom QTableWidgetItem for numerical sorting."""

    def __lt__(self, other):
        """Widget `<`, compares the float(self/other.text()) of the item."""
        try:
            # Handle empty strings or non-numeric data gracefully
            self_val = float(self.text())
            other_val = float(other.text())
            return self_val < other_val
        except (ValueError, TypeError):
            # Fallback to string comparison if conversion fails
            return super().__lt__(other)


class PlayerRoles:
    """Custom Qt item data roles for player information.

    Extends UserRole to store player ID, name, and score data
    in Qt model items beyond standard display text.
    """

    PlayerIdRole = Qt.ItemDataRole.UserRole + 1
    PlayerNameRole = Qt.ItemDataRole.UserRole + 2
    PlayerScoreRole = Qt.ItemDataRole.UserRole + 3


class PlayersTab(QtWidgets.QWidget):
    """Player tab used in GUI."""

    status_message = pyqtSignal(str)
    history_message = pyqtSignal(str)
    dirty = pyqtSignal()
    request_reset_tournament = pyqtSignal()
    request_standings_update = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tournament = None
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.player_group = QtWidgets.QGroupBox("Players")
        self.player_group.setToolTip("Manage players. Right-click a row for actions.")
        player_group_layout = QtWidgets.QVBoxLayout(self.player_group)

        # --- Player Table ---
        self.players_tbl = QtWidgets.QTableWidget()
        self.players_tbl.setToolTip(
            "Registered players. Right-click to Edit/Withdraw/Reactivate/Remove."
        )
        self.players_tbl.setColumnCount(4)  # Name, Rating, Age, Active
        self.players_tbl.setHorizontalHeaderLabels(["Name", "Rating", "Age", "Status"])
        self.players_tbl.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.players_tbl.customContextMenuRequested.connect(
            self.get_player_context_menu
        )
        self.players_tbl.setAlternatingRowColors(True)
        self.players_tbl.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.players_tbl.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.players_tbl.setSortingEnabled(True)

        # Resize columns
        header = self.players_tbl.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.players_tbl.setColumnWidth(1, 110)  # Rating
        self.players_tbl.setColumnWidth(2, 90)  # Age
        self.players_tbl.setColumnWidth(3, 130)  # Status

        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)
        header.setSectionsMovable(True)
        header.setHighlightSections(True)
        # Enable smooth sort arrow animation (Qt6+)
        try:
            header.setAnimated(True)
        except Exception:
            pass

        player_group_layout.addWidget(self.players_tbl)
        self.players_tbl.hide()  # Hide table initially

        self.btn_add_player_detail = QtWidgets.QPushButton(" Add New Player...")
        self.btn_add_player_detail.setToolTip(
            "Open dialog to add a new player with full details."
        )
        self.btn_add_player_detail.clicked.connect(self.add_player_detailed)
        player_group_layout.addWidget(self.btn_add_player_detail)
        self.main_layout.addWidget(self.player_group)

        # Ensure sufficient row height for padded cells
        vheader = self.players_tbl.verticalHeader()
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

    def clean(self) -> None:
        """Clean up all players and reset everything to defaults."""
        self.players_tbl = QtWidgets.QTableWidget()

    def get_player_context_menu(self, point: QtCore.QPoint) -> None:
        """Get the player context menu for a clicked on player.

        Parameters
        ----------
        point : QtCore.QPoint
            point on the player selected
        """
        row = self.players_tbl.rowAt(point.y())
        if row < 0 or not self.tournament:
            return

        player_id_item = self.players_tbl.item(row, 0)
        if not player_id_item:
            return

        player_id = player_id_item.data(Qt.ItemDataRole.UserRole)
        player = self.tournament.players.get(player_id)
        if not player:
            return

        tournament_started = len(self.tournament.rounds_pairings_ids) > 0

        menu = QtWidgets.QMenu(self)
        edit_action = menu.addAction("Edit Player Details...")
        toggle_action_text = (
            "Withdraw Player" if player.is_active else "Reactivate Player"
        )
        toggle_action = menu.addAction(toggle_action_text)
        remove_action = menu.addAction("Remove Player")

        edit_action.setEnabled(not tournament_started)  # type: ignore[union-attr]
        remove_action.setEnabled(not tournament_started)  # type: ignore[union-attr]
        toggle_action.setEnabled(True)  # type: ignore[union-attr]

        action = menu.exec(self.players_tbl.mapToGlobal(point))

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
        elif action == toggle_action:

            # remove player from active Players list
            self.active_players.remove(player.id)
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
                self.players_tbl.removeRow(row)
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
        """Find and updates the QTableWidget row for a given player."""
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
