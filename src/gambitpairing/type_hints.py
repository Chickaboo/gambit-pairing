"""Type hints used in Gambit Pairing."""

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

from typing import List, Literal, Optional, Tuple, TypeAlias

# chess colours
W = Literal["White"]
B = Literal["Black"]
# Basically, white or black
Colour = Literal[W, B]


# List of players
Players = List["Player"]  # type: ignore[name-defined]
# Tuple of player indices in Players
MatchPairing = Tuple[int, int]
# All pairings for one round
RoundSchedule = Tuple[MatchPairing, ...]
# A Tuple containing
Pairings = Tuple[List[Tuple["Player", "Player"]], Optional["Player"]]  # type: ignore[name-defined]
MaybePlayer = Optional["Player"]  # type: ignore[name-defined]

#  LocalWords:  MatchPairing RoundSchedule
