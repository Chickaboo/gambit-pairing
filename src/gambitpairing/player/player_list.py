"""A module containing PlayerList."""

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


class PlayerList(list):
    """A container for a list of `Player` objects.

    This class extends the built-in `list` to store multiple `Player`
    instances and provides convenience methods for filtering, exporting,
    and representing the data.

    Examples
    --------
    Create a list and filter by city:

    >>> players = PlayerList([
    ...     Player("Alice", "Toronto", "123", "2025-12-31", "2100", "2050"),
    ...     Player("Bob", "Vancouver", "456", "2024-08-10", "1800", "1750"),
    ... ])
    >>> toronto_players = players.filter_by_city("Toronto")
    >>> toronto_players
    <PlayerList 1 players>
    """

    def filter_by_city(self, city: str) -> "PlayerList":
        """Return players whose city matches the given name (case-insensitive).

        Parameters
        ----------
        city : str
            The name of the city to match.

        Returns
        -------
        PlayerList
            A new `PlayerList` containing only players whose `city` matches
            the specified value, ignoring case.
        """
        return PlayerList([p for p in self if p.city.lower() == city.lower()])

    def filter_by_min_rating(self, min_rating: int) -> "PlayerList":
        """Return players whose regular rating is greater than or equal to a threshold.

        Parameters
        ----------
        min_rating : int
            The minimum regular rating to filter players.

        Returns
        -------
        PlayerList
            A new `PlayerList` containing only players whose `regular_rating`
            is greater than or equal to `min_rating`.

        Notes
        -----
        This method assumes the `regular_rating` attribute is a numeric string.
        Non-numeric values are ignored in the comparison.
        """
        return PlayerList(
            [
                p
                for p in self
                if p.regular_rating.isdigit() and int(p.regular_rating) >= min_rating
            ]
        )

    def to_dicts(self) -> list[dict]:
        """Convert all players in the list to dictionaries.

        Returns
        -------
        list of dict
            A list where each entry is the result of calling `Player.to_dict()`
            for a player in the list.
        """
        return [p.to_dict() for p in self]

    def __repr__(self) -> str:
        """Representation of the PlayerList.

        Returns
        -------
        str
            A string in the format "<PlayerList N players>", where N is the number
            of players contained in the list.
        """
        return f"<PlayerList {len(self)} players>"
