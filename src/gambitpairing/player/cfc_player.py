"""A CFC chess player."""

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

from datetime import date
from typing import Any, Dict, Optional

from gambitpairing.club import Club
from gambitpairing.player.base_player import Player
from gambitpairing.utils.cfc_api import get_cfc_player_info


class CfcPlayer(Player):
    """Represents a Chess Federation of Canada (CFC) player.

    This class represents a single player entry containing identifying information,
    membership details, and ratings.

    Attributes
    ----------
    name : str
        Full name of the player.
    phone : Optional[str]
        Player's phone number
    email : Optional[str]
        Player's email address
    club : Optional[Club]
        Player's chess club
    gender : Optional[str]
        Player's gender
    date_of_birth : Optional[datetime]
        Player's date of birth
    cfc_id : Optional[str]
        Unique CFC ID number assigned by the Canadian Chess Federation
    cfc_expiry : Optional[str]
        Membership expiry date in YYYY-MM-DD format
    regular_rating : Optional[int]
        Regular time control rating
    quick_rating : Optional[int]
        Quick time control rating
    city : Optional[str]
        City of residence
    """

    def __init__(
        self,
        name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        club: Optional[Club] = None,
        gender: Optional[str] = None,
        cfc_id: Optional[str] = None,
        cfc_expiry: Optional[str] = None,
        regular_rating: Optional[int] = None,
        quick_rating: Optional[int] = None,
        city: Optional[str] = None,
    ) -> None:
        super().__init__(
            name=name,
            phone=phone,
            email=email,
            club=club,
            gender=gender,
            date_of_birth=date_of_birth,
        )
        self.cfc_id = cfc_id
        self.cfc_expiry = cfc_expiry
        self.regular_rating = regular_rating
        self.quick_rating = quick_rating
        self.city = city

    @classmethod
    def from_id(cls, cfc_id: str) -> "CfcPlayer":
        """Create a CfcPlayer instance from a CFC ID.

        Parameters
        ----------
        cfc_id : str
            The CFC ID to lookup

        Returns
        -------
        CfcPlayer
            A new CfcPlayer instance with data from the CFC API
        """
        data = get_cfc_player_info(cfc_id)
        return cls(
            name=f"{data['name_first']} {data['name_last']}",
            cfc_id=str(data["cfc_id"]),
            cfc_expiry=data["cfc_expiry"],
            regular_rating=data["regular_rating"],
            quick_rating=data["quick_rating"],
        )

    @classmethod
    def from_dict(cls, player_data: Dict[str, Any]) -> "CfcPlayer":
        """Create a CFC Player instance from serialized data.

        Parameters
        ----------
        player_data : Dict[str, Any]
            Dictionary of player attributes

        Returns
        -------
        CfcPlayer
            A new CfcPlayer instance
        """
        gender = player_data.get("gender") or player_data.get("sex")

        player = cls(
            name=player_data["name"],
            phone=player_data.get("phone"),
            email=player_data.get("email"),
            club=player_data.get("club"),
            gender=gender,
            date_of_birth=player_data.get("dob"),
            cfc_id=player_data.get("cfc_id"),
            cfc_expiry=player_data.get("cfc_expiry"),
            regular_rating=player_data.get("regular_rating"),
            quick_rating=player_data.get("quick_rating"),
        )

        for key, value in player_data.items():
            if hasattr(player, key) and not key.startswith("_"):
                setattr(player, key, value)

        return player

    def __repr__(self) -> str:
        """Str representation of the Player instance.

        Returns
        -------
        str
            A compact string containing the player's name and CFC ID.
        """
        return f"<CFC Player {self.name} (CFC ID: {self.cfc_id})>"


#  LocalWords:  YYYY
