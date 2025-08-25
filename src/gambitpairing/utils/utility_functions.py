"""Utility function used in Gambit Pairing."""

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


import random

from PyQt6 import QtCore
from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import QListWidget


# --- Utility Functions ---
def generate_id(prefix: str = "item_") -> str:
    """Generate a simple unique ID."""
    return f"{prefix}{random.randint(100000, 999999)}_{int(QDateTime.currentMSecsSinceEpoch())}"


def resize_list_to_show_all_items(list_widget: QListWidget) -> None:
    """Resize QListWidget to show all items without scrolling."""
    if list_widget.count() == 0:
        return

    # Calculate total height needed
    total_height = 0
    for i in range(list_widget.count()):
        total_height += list_widget.sizeHintForRow(i)

    # Add frame margins
    frame_height = list_widget.frameWidth() * 2

    # Disable vertical scrollbar and set height
    list_widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    list_widget.setFixedHeight(total_height + frame_height)


def is_round_robin(tournament) -> bool:
    """Is a tournament round robin."""
    return getattr(tournament, "pairing_system", False) == "round_robin"
