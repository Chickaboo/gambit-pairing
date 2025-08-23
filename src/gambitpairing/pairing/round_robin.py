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

"""
Round Robin Tournament Pairing System

This module implements FIDE-compliant round-robin tournament pairings using
Berger tables. It supports tournaments with 3-16 players and handles both
even and odd numbers of players (with bye assignments for odd numbers).

The Berger tables ensure that:
- Each player plays every other player exactly once
- Color balance is maintained as much as possible
- Bye assignments follow FIDE rules (highest number gets bye)

Example:
    >>> from gambitpairing.player import Player
    >>> players = [Player("Alice"), Player("Bob"), Player("Charlie")]
    >>> rr = RoundRobin(players)
    >>> first_round = rr.get_round_pairings(1)
    >>> print(first_round)
"""

from typing import Iterable, List, Optional, Tuple

from gambitpairing.exceptions import PairingException
from gambitpairing.player import Player
from gambitpairing.type_hints import Pairings, Players, RoundSchedule
from gambitpairing.utils import setup_logger

logger = setup_logger(__name__)

# Type aliases for clarity
BergerTable = Tuple[RoundSchedule, ...]  # Complete tournament schedule


# FIDE Berger Tables for Round-Robin Tournaments
#
# These tables define the pairing schedule for round-robin tournaments.
# Player numbers are 0-indexed (adjusted from FIDE's 1-indexed tables).
# For odd numbers of players, the highest index represents a bye.
#
# Format: Each tuple represents one round, containing tuples of (player1, player2)
BERGER_TABLES: dict[str, BergerTable] = {
    "3-4": (
        ((0, 3), (1, 2)),
        ((3, 2), (0, 1)),
        ((1, 3), (2, 0)),
    ),
    "5-6": (
        ((0, 5), (1, 4), (2, 3)),
        ((5, 3), (4, 2), (0, 1)),
        ((1, 5), (2, 0), (3, 4)),
        ((5, 4), (0, 3), (1, 2)),
        ((2, 5), (3, 1), (4, 0)),
    ),
    "7-8": (
        ((0, 7), (1, 6), (2, 5), (3, 4)),
        ((7, 4), (5, 3), (6, 2), (0, 1)),
        ((1, 7), (2, 0), (3, 6), (4, 5)),
        ((7, 5), (6, 4), (0, 3), (1, 2)),
        ((2, 7), (3, 1), (4, 0), (5, 6)),
        ((7, 6), (0, 5), (1, 4), (2, 3)),
        ((3, 7), (4, 2), (5, 1), (6, 0)),
    ),
    "9-10": (
        ((0, 9), (1, 8), (2, 7), (3, 6), (4, 5)),
        ((9, 5), (6, 4), (7, 3), (8, 2), (0, 1)),
        ((1, 9), (2, 0), (3, 8), (4, 7), (5, 6)),
        ((9, 6), (7, 5), (8, 4), (0, 3), (1, 2)),
        ((2, 9), (3, 1), (4, 0), (5, 8), (6, 7)),
        ((9, 7), (8, 6), (0, 5), (1, 4), (2, 3)),
        ((3, 9), (4, 2), (5, 1), (6, 0), (7, 8)),
        ((9, 8), (0, 7), (1, 6), (2, 5), (3, 4)),
        ((4, 9), (5, 3), (6, 2), (7, 1), (8, 0)),
    ),
    "11-12": (
        ((0, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)),
        ((11, 6), (7, 5), (8, 4), (9, 3), (10, 2), (0, 1)),
        ((1, 11), (2, 0), (3, 10), (4, 9), (5, 8), (6, 7)),
        ((11, 7), (8, 6), (9, 5), (10, 4), (0, 3), (1, 2)),
        ((2, 11), (3, 1), (4, 0), (5, 10), (6, 9), (7, 8)),
        ((11, 8), (9, 7), (10, 6), (0, 5), (1, 4), (2, 3)),
        ((3, 11), (4, 2), (5, 1), (6, 0), (7, 10), (8, 9)),
        ((11, 9), (10, 8), (0, 7), (1, 6), (2, 5), (3, 4)),
        ((4, 11), (5, 3), (6, 2), (7, 1), (8, 0), (9, 10)),
        ((11, 10), (0, 9), (1, 8), (2, 7), (3, 6), (4, 5)),
        ((5, 11), (6, 4), (7, 3), (8, 2), (9, 1), (10, 0)),
    ),
    "13-14": (
        ((0, 13), (1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)),
        ((13, 7), (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (0, 1)),
        ((1, 13), (2, 0), (3, 12), (4, 11), (5, 10), (6, 9), (7, 8)),
        ((13, 8), (9, 7), (10, 6), (11, 5), (12, 4), (0, 3), (1, 2)),
        ((2, 13), (3, 1), (4, 0), (5, 12), (6, 11), (7, 10), (8, 9)),
        ((13, 9), (10, 8), (11, 7), (12, 6), (0, 5), (1, 4), (2, 3)),
        ((3, 13), (4, 2), (5, 1), (6, 0), (7, 12), (8, 11), (9, 10)),
        ((13, 10), (11, 9), (12, 8), (0, 7), (1, 6), (2, 5), (3, 4)),
        ((4, 13), (5, 3), (6, 2), (7, 1), (8, 0), (9, 12), (10, 11)),
        ((13, 11), (12, 10), (0, 9), (1, 8), (2, 7), (3, 6), (4, 5)),
        ((5, 13), (6, 4), (7, 3), (8, 2), (9, 1), (10, 0), (11, 12)),
        ((13, 12), (0, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)),
        ((6, 13), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1), (12, 0)),
    ),
    "15-16": (
        ((0, 15), (1, 14), (2, 13), (3, 12), (4, 11), (5, 10), (6, 9), (7, 8)),
        ((15, 8), (9, 7), (10, 6), (11, 5), (12, 4), (13, 3), (14, 2), (0, 1)),
        ((1, 15), (2, 0), (3, 14), (4, 13), (5, 12), (6, 11), (7, 10), (8, 9)),
        ((15, 9), (10, 8), (11, 7), (12, 6), (13, 5), (14, 4), (0, 3), (1, 2)),
        ((2, 15), (3, 1), (4, 0), (5, 14), (6, 13), (7, 12), (8, 11), (9, 10)),
        ((15, 10), (11, 9), (12, 8), (13, 7), (14, 6), (0, 5), (1, 4), (2, 3)),
        ((3, 15), (4, 2), (5, 1), (6, 0), (7, 14), (8, 13), (9, 12), (10, 11)),
        ((15, 11), (12, 10), (13, 9), (14, 8), (0, 7), (1, 6), (2, 5), (3, 4)),
        ((4, 15), (5, 3), (6, 2), (7, 1), (8, 0), (9, 14), (10, 13), (11, 12)),
        ((15, 12), (13, 11), (14, 10), (0, 9), (1, 8), (2, 7), (3, 6), (4, 5)),
        ((5, 15), (6, 4), (7, 3), (8, 2), (9, 1), (10, 0), (11, 14), (12, 13)),
        ((15, 13), (14, 12), (0, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)),
        ((6, 15), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1), (12, 0), (13, 14)),
        ((15, 14), (0, 13), (1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)),
        ((7, 15), (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (13, 1), (14, 0)),
    ),
}


class RoundRobin:
    """
    A FIDE-compliant round-robin chess tournament implementation.

    This class manages the complete pairing schedule for a round-robin tournament
    using Berger tables. It supports 3-16 players and automatically handles
    bye assignments for tournaments with odd numbers of players.

    Attributes
    ----------
        players: Immutable tuple of players in tournament order
        berger_table: The Berger table used for this tournament size
        number_of_rounds: Total number of rounds in the tournament
        bye_number: Player index that receives byes (None for even tournaments)
        round_pairings: List of pairings for each round

    Example
    -------
        >>> players = [Player("Alice"), Player("Bob"), Player("Charlie"), Player("David")]
        >>> tournament = RoundRobin(players)
        >>> tournament.number_of_rounds
        3
        >>> first_round = tournament.get_round_pairings(1)
    """

    def __init__(self, players: Iterable[Player]) -> None:
        """
        Initialize a round-robin tournament.

        Parameters
        ----------
            players: Iterable of Player objects (3-16 players supported)

        Raises
        ------
            PairingException: If number of players is outside the 3-16 range
        """
        self.players = tuple(players)  # Immutable to preserve order
        n_players = len(self.players)

        if not (3 <= n_players <= 16):
            logger.error("Invalid player count for round robin: %d", n_players)
            raise PairingException(
                f"Round robin tournaments support 3-16 players, got {n_players}"
            )

        # Select appropriate Berger table and set bye player if needed
        self._select_berger_table(n_players)

        # Pre-compute all round pairings
        self._generate_all_pairings()

    def _select_berger_table(self, n_players: int) -> None:
        """
        Select the appropriate Berger table for the given number of players.

        Args:
            n_players: Number of players in the tournament
        """
        self.bye_number: Optional[int] = None

        if n_players >= 15:
            self.berger_table = BERGER_TABLES["15-16"]
            if n_players % 2 != 0:
                self.bye_number = 15
            logger.info("Using 15-16 player Berger table")

        elif n_players >= 13:
            self.berger_table = BERGER_TABLES["13-14"]
            if n_players % 2 != 0:
                self.bye_number = 13
            logger.info("Using 13-14 player Berger table")

        elif n_players >= 11:
            self.berger_table = BERGER_TABLES["11-12"]
            if n_players % 2 != 0:
                self.bye_number = 11
            logger.info("Using 11-12 player Berger table")

        elif n_players >= 9:
            self.berger_table = BERGER_TABLES["9-10"]
            if n_players % 2 != 0:
                self.bye_number = 9
            logger.info("Using 9-10 player Berger table")

        elif n_players >= 7:
            self.berger_table = BERGER_TABLES["7-8"]
            if n_players % 2 != 0:
                self.bye_number = 7
            logger.info("Using 7-8 player Berger table")

        elif n_players >= 5:
            self.berger_table = BERGER_TABLES["5-6"]
            if n_players % 2 != 0:
                self.bye_number = 5
            logger.info("Using 5-6 player Berger table")

        else:  # 3-4 players
            self.berger_table = BERGER_TABLES["3-4"]
            if n_players % 2 != 0:
                self.bye_number = 3
            logger.info("Using 3-4 player Berger table")

        self.number_of_rounds = len(self.berger_table)

    def _generate_all_pairings(self) -> None:
        """Generate pairings for all rounds in the tournament."""
        logger.info(
            "Generating pairings for %d players using table: %s",
            len(self.players),
            self.berger_table,
        )

        self.round_pairings: List[Pairings] = []

        for round_idx in range(self.number_of_rounds):
            pairings = self._generate_round_pairings(round_idx)
            self.round_pairings.append(pairings)

        logger.info(
            "Generated pairings for %d rounds with %d players",
            len(self.round_pairings),
            len(self.players),
        )

    def _generate_round_pairings(self, round_idx: int) -> Pairings:
        """
        Generate pairings for a specific round.

        Args:
            round_idx: 0-indexed round number

        Returns:
            Pairings tuple containing (matches, bye_player)

        Raises:
            PairingException: If round_idx is invalid
        """
        if not (0 <= round_idx < len(self.berger_table)):
            raise PairingException(
                f"Round {round_idx} not valid for tournament with "
                f"{len(self.berger_table)} rounds"
            )

        round_schedule = self.berger_table[round_idx]
        logger.debug("Processing round %d: %s", round_idx, round_schedule)

        matches = []
        bye_player = None

        for match_pairing in round_schedule:
            player1_idx, player2_idx = match_pairing

            # Check if this pairing involves the bye slot
            if self.bye_number is not None and self.bye_number in match_pairing:
                # Find the real player (not the bye number)
                real_player_idx = (
                    player1_idx if player1_idx != self.bye_number else player2_idx
                )

                # Only assign bye if the player exists in our tournament
                if real_player_idx < len(self.players):
                    bye_player = self.players[real_player_idx]
                    logger.debug(
                        "Bye assigned to player %d: %s", real_player_idx, bye_player
                    )
                continue

            # Both players must exist in our tournament
            if player1_idx < len(self.players) and player2_idx < len(self.players):

                match = (self.players[player1_idx], self.players[player2_idx])
                matches.append(match)
                logger.debug(
                    "Match created: %s vs %s",
                    self.players[player1_idx],
                    self.players[player2_idx],
                )

        logger.info(
            "Round %d: %d matches, bye: %s", round_idx + 1, len(matches), bye_player
        )

        return (tuple(matches), bye_player)

    def get_round_pairings(self, round_number: int) -> Pairings:
        """
        Get pairings for a specific round.

        Args:
            round_number: 1-indexed round number (1 = first round)

        Returns:
            Pairings for the specified round

        Raises:
            PairingException: If round_number is invalid or no pairings exist
        """
        if not self.round_pairings:
            raise PairingException("No round pairings have been generated")

        if not (1 <= round_number <= len(self.round_pairings)):
            raise PairingException(
                f"Round {round_number} is not valid. Tournament has "
                f"{len(self.round_pairings)} rounds (1-{len(self.round_pairings)})"
            )

        return self.round_pairings[round_number - 1]  # Convert to 0-indexed

    def get_all_pairings(self) -> Tuple[Pairings, ...]:
        """
        Get pairings for all rounds.

        Returns:
            Tuple containing pairings for each round
        """
        return tuple(self.round_pairings)

    def get_player_schedule(self, player: Player) -> List[Tuple[int, Optional[Player]]]:
        """
        Get the complete schedule for a specific player.

        Args:
            player: The player to get schedule for

        Returns:
            List of tuples (round_number, opponent), where opponent is None for bye rounds

        Raises:
            PairingException: If player is not in the tournament
        """
        if player not in self.players:
            raise PairingException(f"Player {player} is not in this tournament")

        schedule = []
        for round_idx, (matches, bye_player) in enumerate(self.round_pairings):
            round_num = round_idx + 1
            opponent = None

            # Check if player has a bye
            if bye_player == player:
                schedule.append((round_num, None))
                continue

            # Find opponent in matches
            for match in matches:
                if player in match:
                    opponent = match[0] if match[1] == player else match[1]
                    break

            schedule.append((round_num, opponent))

        return schedule

    def __str__(self) -> str:
        """String representation of the tournament."""
        lines = [
            f"Round Robin Tournament: {len(self.players)} players, {self.number_of_rounds} rounds"
        ]

        for i, (matches, bye_player) in enumerate(self.round_pairings):
            round_num = i + 1
            lines.append(f"\nRound {round_num}:")

            for match in matches:
                lines.append(f"  {match[0]} vs {match[1]}")

            if bye_player:
                lines.append(f"  Bye: {bye_player}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        """Detailed representation of the tournament."""
        return (
            f"RoundRobin(players={len(self.players)}, "
            f"rounds={self.number_of_rounds}, "
            f"bye_player_index={self.bye_number})"
        )


def create_round_robin(players: Players) -> RoundRobin:
    """
    Create a complete FIDE round-robin tournament.

    Args:
        players: Collection of Player objects to be paired

    Returns:
        the created RoundRobin class

    Raises:
        PairingException: If the number of players is not between 3-16

    Example:
        >>> players = [Player("Alice"), Player("Bob"), Player("Charlie")]
        >>> round_robin = create_round_robin(players)
        >>> len(round_robin.players)  # Number of players
    """
    tournament = RoundRobin(players)
    logger.info("Round Robin tournament created: %s", tournament)
    return tournament


# Example usage and testing
if __name__ == "__main__":
    # Test with 3 players (odd number)
    players_3 = [Player("Alice"), Player("Bob"), Player("Charlie")]

    print("=== 3 Player Tournament ===")
    tournament = RoundRobin(players_3)
    print(tournament)
    print(f"\nAlice's schedule: {tournament.get_player_schedule(players_3[0])}")

    # Test with 4 players (even number)
    players_4 = [Player("Alice"), Player("Bob"), Player("Charlie"), Player("David")]

    print("\n=== 4 Player Tournament ===")
    tournament_4 = RoundRobin(players_4)
    print(tournament_4)

#  LocalWords:  BergerTable RoundSchedule MatchPairing RoundRobin
