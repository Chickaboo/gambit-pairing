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


class CfcPlayer:
    """
    Container for a CFC player record.

    This class represents a single player entry returned by the CFC
    ratings search, containing identifying information, membership
    details, and ratings.

    Parameters
    ----------
    name : str
        Full name of the player.
    city : str
        City of residence.
    cfc_id : str
        Unique CFC ID number assigned by the Canadian Chess Federation.
    expiry : str
        Membership expiry date in YYYY-MM-DD format.
    regular_rating : str
        Regular time control rating as a string.
    quick_rating : str
        Quick time control rating as a string.

    Examples
    --------
    >>> p = Player("Alice Smith", "Toronto", "123456", "2025-12-31", "2100", "2050")
    >>> print(p)
    <Player Alice Smith (CFC ID: 123456)>
    >>> p.to_dict()
    {'Name': 'Alice Smith',
     'City': 'Toronto',
     'CFC ID': '123456',
     'Expiry': '2025-12-31',
     'Regular Rating': '2100',
     'Quick Rating': '2050'}
    """

    def __init__(
        self,
        name: str,
        city: str,
        cfc_id: str,
        expiry: str,
        regular_rating: str,
        quick_rating: str,
    ):
        self.name = name
        self.city = city
        self.cfc_id = cfc_id
        self.expiry = expiry
        self.regular_rating = regular_rating
        self.quick_rating = quick_rating

    def __repr__(self) -> str:
        """Str representation of the Player instance.

        Returns
        -------
        str
            A compact string containing the player's name and CFC ID.
        """
        return f"<Player {self.name} (CFC ID: {self.cfc_id})>"

    def to_dict(self) -> dict:
        """
        Convert the player data to a dictionary.

        Returns
        -------
        dict
            Dictionary containing:
            - 'Name': str
            - 'City': str
            - 'CFC ID': str
            - 'Expiry': str
            - 'Regular Rating': str
            - 'Quick Rating': str
        """
        return {
            "Name": self.name,
            "City": self.city,
            "CFC ID": self.cfc_id,
            "Expiry": self.expiry,
            "Regular Rating": self.regular_rating,
            "Quick Rating": self.quick_rating,
        }
