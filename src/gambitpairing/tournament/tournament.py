"""Relating to a Chess Tournament managed by Gambit Pairing."""

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


import functools
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from gambitpairing.constants import (
    BYE_SCORE,
    DEFAULT_TIEBREAK_SORT_ORDER,
    DRAW_SCORE,
    LOSS_SCORE,
    TB_CUMULATIVE,
    TB_CUMULATIVE_OPP,
    TB_HEAD_TO_HEAD,
    TB_MEDIAN,
    TB_MOST_BLACKS,
    TB_SOLKOFF,
    TB_SONNENBORN_BERGER,
    WIN_SCORE,
)
from gambitpairing.pairing.dutch_swiss import create_dutch_swiss_pairings
from gambitpairing.pairing.round_robin import RoundRobin, create_round_robin
from gambitpairing.player import Player
from gambitpairing.type_hints import B, Pairings, W


class Tournament:
    """Manages the tournament state, pairings, results, and tiebreakers."""

    def __init__(
        self,
        name: str,
        players: List[Player],
        num_rounds: int,
        tiebreak_order: Optional[List[str]] = None,
        pairing_system: str = "dutch_swiss",
    ) -> None:
        self.name = name
        self.players: Dict[str, Player] = {p.id: p for p in players}
        self.num_rounds: int = num_rounds
        self.tiebreak_order: List[str] = tiebreak_order or list(
            DEFAULT_TIEBREAK_SORT_ORDER
        )
        self.rounds_pairings_ids: List[List[Tuple[str, str]]] = []
        self.rounds_byes_ids: List[Optional[str]] = []
        self.previous_matches: Set[frozenset[str]] = set()
        self.manual_pairings: Dict[int, Dict[str, str]] = {}
        self.pairing_system: str = pairing_system

        # internal state, not to be touched
        self._started = False

    @property
    def started(self) -> bool:
        """The tournament is underway."""
        return self._started

    @property
    def player_list(self) -> list[Player]:
        """Get all players in the tournament.

        Returns
        -------
        list
            All the players in the Tournament
        """
        return list(self.players.values())

    def remove_player(self, id: str) -> None:
        """Remove a single player by id."""
        if id in self.players:
            del self.players[id]
        else:
            raise KeyError(f"No player with id {player_id}")

    def get_players(self, active_only=False) -> List[Player]:
        """Get the players in this tournament.

        Parameters
        ----------
        active_only=False
            Only active players

        Returns
        -------
        List[Players]
            The Tournament player list
        """
        players = list(self.players.values())
        if active_only:
            return [p for p in players if p.is_active]
        return players

    def _get_active_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.is_active]

    def _get_eligible_bye_player(
        self, potential_bye_players: List[Player]
    ) -> Optional[Player]:
        """Determine the bye player according to Swiss rules.

        Parameters
        ----------
        potential_bye_players : List[Players]
            A list of players who can get a bye.

        Notes
        -----
        Priority: Active player who has not yet received a bye, lowest score, then lowest rating.
        Fallback: If all have received a bye, the active player with the lowest score, then rating, gets a second bye.
        """
        if not potential_bye_players:
            return None

        active_players = [p for p in potential_bye_players if p.is_active]
        if not active_players:
            logging.debug(
                "_get_eligible_bye_player: No active players in potential list."
            )
            return None

        eligible_for_first_bye = [p for p in active_players if not p.has_received_bye]

        if eligible_for_first_bye:
            eligible_for_first_bye.sort(key=lambda p: (p.score, p.rating, p.name))
            logging.info(
                f"Assigning first bye to: {eligible_for_first_bye[0].name} (Score: {eligible_for_first_bye[0].score}, Rating: {eligible_for_first_bye[0].rating})"
            )
            return eligible_for_first_bye[0]
        else:
            # All active players in the list have already received a bye.
            # A second bye must be assigned if a bye is necessary (e.g. USCF 29E2).
            logging.warning(
                f"All potential bye candidates ({[p.name for p in active_players]}) "
                f"have already received a bye. Assigning a second bye as a last resort."
            )
            active_players.sort(key=lambda p: (p.score, p.rating, p.name))
            logging.info(
                f"Assigning second bye to: {active_players[0].name} (Score: {active_players[0].score}, Rating: {active_players[0].rating})"
            )
            return active_players[0]

    def create_pairings(
        self, current_round: int, allow_repeat_pairing_callback=None
    ) -> Pairings:
        """Generate pairings for the next round using the selected pairing system."""
        active_players = self._get_active_players()
        if self.pairing_system == "dutch_swiss":
            pairings, bye_player, round_pairings_ids, bye_player_id = (
                create_dutch_swiss_pairings(
                    active_players,
                    current_round,
                    self.previous_matches,
                    self._get_eligible_bye_player,
                    allow_repeat_pairing_callback,
                    self.num_rounds,
                )
            )
            self.rounds_pairings_ids.append(round_pairings_ids)
            self.rounds_byes_ids.append(bye_player_id)
            return pairings, bye_player
        elif self.pairing_system == "round_robin":
            # Check if we already have a round robin
            if hasattr(self, "round_robin"):
                # Get the pairings for this round
                pairings_result = self.round_robin.get_round_pairings(current_round)
                pairings, bye_player = pairings_result

                # Check if we've already stored these pairings
                round_idx = current_round - 1  # Convert to 0-indexed
                if round_idx >= len(self.rounds_pairings_ids):
                    # Convert to player IDs for storage
                    round_pairings_ids = []
                    for player1, player2 in pairings:
                        round_pairings_ids.append((player1.id, player2.id))

                    bye_player_id = bye_player.id if bye_player else None

                    # Ensure we have enough rounds stored
                    while len(self.rounds_pairings_ids) <= round_idx:
                        self.rounds_pairings_ids.append([])
                    while len(self.rounds_byes_ids) <= round_idx:
                        self.rounds_byes_ids.append(None)

                    self.rounds_pairings_ids[round_idx] = round_pairings_ids
                    self.rounds_byes_ids[round_idx] = bye_player_id

                return pairings, bye_player

            # else create new round robin
            active_players = self._get_active_players()
            self.round_robin: RoundRobin = create_round_robin(active_players)

            # Update tournament rounds to match round robin requirements
            if self.num_rounds != self.round_robin.number_of_rounds:
                logging.info(
                    f"Updating tournament rounds from {self.num_rounds} to {self.round_robin.number_of_rounds} for round robin"
                )
                self.num_rounds = self.round_robin.number_of_rounds

            # Get the pairings for this round
            pairings_result = self.round_robin.get_round_pairings(current_round)
            pairings, bye_player = pairings_result

            # Convert to player IDs for storage
            round_pairings_ids = []
            for player1, player2 in pairings:
                round_pairings_ids.append((player1.id, player2.id))

            bye_player_id = bye_player.id if bye_player else None

            # Ensure we have the right number of rounds
            round_idx = current_round - 1  # Convert to 0-indexed
            while len(self.rounds_pairings_ids) <= round_idx:
                self.rounds_pairings_ids.append([])
            while len(self.rounds_byes_ids) <= round_idx:
                self.rounds_byes_ids.append(None)

            self.rounds_pairings_ids[round_idx] = round_pairings_ids
            self.rounds_byes_ids[round_idx] = bye_player_id
            return pairings, bye_player
        elif self.pairing_system == "manual":
            # For manual pairing, return empty pairings - they will be set manually
            self.rounds_pairings_ids.append([])
            self.rounds_byes_ids.append(None)
            return [], None
        else:
            raise NotImplementedError(
                f"Pairing system '{self.pairing_system}' is not implemented."
            )

    def get_pairings_for_round(self, round_index: int) -> Pairings:
        """Retrieve the pairings and bye player for a given round index."""
        if not (0 <= round_index < len(self.rounds_pairings_ids)):
            return [], None

        pairings_ids = self.rounds_pairings_ids[round_index]
        bye_player_id = self.rounds_byes_ids[round_index]

        pairings = []
        for p1_id, p2_id in pairings_ids:
            p1 = self.players.get(p1_id)
            p2 = self.players.get(p2_id)
            if p1 and p2:
                pairings.append((p1, p2))

        bye_player = self.players.get(bye_player_id) if bye_player_id else None
        return pairings, bye_player

    def manually_adjust_pairing(
        self, round_index: int, player1_id: str, new_opponent_id: str
    ) -> bool:
        """Allow manual adjustment of one player's opponent in a specific round's pairings."""
        if round_index < 0 or round_index >= len(self.rounds_pairings_ids):
            logging.error(f"Manual Adjust: Invalid round index {round_index}.")
            return False
        if round_index < self.get_completed_rounds():
            logging.error(
                f"Manual Adjust: Cannot adjust pairings for completed round {round_index+1}."
            )
            return False

        current_pairings_ids_for_round = self.rounds_pairings_ids[round_index]

        p1 = self.players.get(player1_id)
        new_opp = self.players.get(new_opponent_id)

        if not p1 or not new_opp:
            logging.error(
                "Manual Adjust: Player or new opponent not found in master player list."
            )
            return False
        if p1 == new_opp:
            logging.warning(
                "Manual Adjust: Player cannot be paired against themselves."
            )
            return False

        # Store original pairings for logging/reversion if needed (complex)
        if round_index not in self.manual_pairings:
            self.manual_pairings[round_index] = {}

        # Find p1's current pairing and original opponent (p1_orig_opp)
        p1_orig_opp_id = None
        p1_pair_idx = -1
        p1_was_white = False

        for idx, (w_id, b_id) in enumerate(current_pairings_ids_for_round):
            if w_id == player1_id:
                p1_orig_opp_id = b_id
                p1_pair_idx = idx
                p1_was_white = True
                break
            elif b_id == player1_id:
                p1_orig_opp_id = w_id
                p1_pair_idx = idx
                p1_was_white = False
                break

        if p1_pair_idx == -1:  # p1 might be the bye player
            current_bye_id = self.rounds_byes_ids[round_index]
            if current_bye_id == player1_id:  # p1 was bye, now paired with new_opp
                # new_opp must have been paired or bye. Find new_opp's original pairing.
                # (This logic becomes complex quickly: swapping a bye player with a paired player)
                logging.warning(
                    f"Manual Adjust: Player {p1.name} was bye. Trying to pair with {new_opp.name}."
                )
                # For simplicity, this case might need more dedicated logic or be disallowed.
                # Assuming p1 was paired for now.
            else:
                logging.error(
                    f"Manual Adjust: Player {p1.name} not found in pairings or bye list for round {round_index+1}."
                )
                return False

        if p1_orig_opp_id == new_opponent_id:
            logging.warning(
                f"Manual Adjust: Player {p1.name} is already paired with {new_opp.name}."
            )
            return True  # No change needed, but not an error

        # Find new_opp's current pairing and their original opponent (new_opp_orig_opp)
        new_opp_orig_opp_id = None
        new_opp_pair_idx = -1
        new_opp_was_white = False

        for idx, (w_id, b_id) in enumerate(current_pairings_ids_for_round):
            if w_id == new_opponent_id:
                new_opp_orig_opp_id = b_id
                new_opp_pair_idx = idx
                new_opp_was_white = True
                break
            elif b_id == new_opponent_id:
                new_opp_orig_opp_id = w_id
                new_opp_pair_idx = idx
                ## new_opp_was_white not used?
                new_opp_was_white = False
                break

        # Case 1: new_opp was also paired (most common)
        if new_opp_pair_idx != -1 and new_opp_orig_opp_id is not None:
            # Record changes before making them
            self.manual_pairings[round_index][player1_id] = p1_orig_opp_id
            self.manual_pairings[round_index][new_opponent_id] = new_opp_orig_opp_id
            if p1_orig_opp_id:
                self.manual_pairings[round_index][p1_orig_opp_id] = player1_id
            if new_opp_orig_opp_id:
                self.manual_pairings[round_index][new_opp_orig_opp_id] = new_opponent_id

            # Pair p1 with new_opp. Retain p1's color if possible, or re-evaluate.
            # For simplicity, let's assume p1 keeps original color slot against new_opp.
            if p1_was_white:
                current_pairings_ids_for_round[p1_pair_idx] = (
                    player1_id,
                    new_opponent_id,
                )
            else:
                current_pairings_ids_for_round[p1_pair_idx] = (
                    new_opponent_id,
                    player1_id,
                )

            # Pair p1_orig_opp with new_opp_orig_opp.
            # Retain p1_orig_opp's color slot if possible.
            if p1_orig_opp_id and new_opp_orig_opp_id:  # Both original opponents exist
                if (
                    new_opp_pair_idx != p1_pair_idx
                ):  # Ensure they were from different original pairs
                    if not p1_was_white:  # p1 was black, so p1_orig_opp was white
                        current_pairings_ids_for_round[new_opp_pair_idx] = (
                            p1_orig_opp_id,
                            new_opp_orig_opp_id,
                        )
                    else:  # p1 was white, so p1_orig_opp was black
                        current_pairings_ids_for_round[new_opp_pair_idx] = (
                            new_opp_orig_opp_id,
                            p1_orig_opp_id,
                        )
                # If new_opp_pair_idx == p1_pair_idx, it means we are swapping partners within the same game.
                # e.g. (A,B) and (C,D). Change A vs B to A vs C. Then B should play D.
                # p1_pair_idx held (A,B). new_opp_pair_idx held (C,D).
                # current_pairings_ids_for_round[p1_pair_idx] becomes (A,C) (if A was white)
                # current_pairings_ids_for_round[new_opp_pair_idx] should become (B,D) (if B was white against A, now B plays D)
                # This needs careful handling of who was white for p1_orig_opp and new_opp_orig_opp.
                # The current logic assumes new_opp_pair_idx refers to new_opp's original game.
                # This re-pairing of p1_orig_opp and new_opp_orig_opp is the "swap partners" part.
            elif p1_orig_opp_id:  # new_opp_orig_opp_id was None (new_opp was bye)
                # p1_orig_opp now gets a bye.
                current_bye_id = self.rounds_byes_ids[round_index]
                if current_bye_id is not None and current_bye_id != new_opponent_id:
                    logging.error(
                        "Manual Adjust: Complex bye scenario, cannot auto-assign new bye."
                    )
                    return False
                self.rounds_byes_ids[round_index] = p1_orig_opp_id
                # Remove new_opp's original pairing (which was effectively with a bye)
                if new_opp_pair_idx != p1_pair_idx and new_opp_pair_idx < len(
                    current_pairings_ids_for_round
                ):  # if new_opp was not bye but paired
                    # This case is tricky. if new_opp_orig_opp_id is None, new_opp was the bye.
                    # Then self.rounds_byes_ids[round_index] should have been new_opponent_id.
                    # And now new_opp is paired with p1. p1_orig_opp becomes the new bye.
                    logging.info(
                        f"Manual Adjust: {new_opp.name} was bye, now paired. {self.players.get(p1_orig_opp_id).name if p1_orig_opp_id else 'Original opponent of p1'} becomes bye."
                    )
            elif new_opp_orig_opp_id:  # p1_orig_opp_id was None (p1 was bye)
                # new_opp_orig_opp now gets a bye.
                # Similar logic as above.
                logging.info(
                    f"Manual Adjust: {p1.name} was bye, now paired. {self.players.get(new_opp_orig_opp_id).name if new_opp_orig_opp_id else 'Original opponent of new_opp'} becomes bye."
                )

        # Case 2: new_opp was the bye player
        elif self.rounds_byes_ids[round_index] == new_opponent_id:
            logging.info(
                f"Manual Adjust: Pairing {p1.name} with {new_opp.name} (who was bye). {self.players.get(p1_orig_opp_id).name if p1_orig_opp_id else 'P1s original opponent'} will now be bye."
            )
            self.manual_pairings[round_index][player1_id] = p1_orig_opp_id
            self.manual_pairings[round_index][new_opponent_id] = None  # Was bye
            if p1_orig_opp_id:
                self.manual_pairings[round_index][p1_orig_opp_id] = player1_id

            # Pair p1 with new_opp
            if p1_was_white:
                current_pairings_ids_for_round[p1_pair_idx] = (
                    player1_id,
                    new_opponent_id,
                )
            else:
                current_pairings_ids_for_round[p1_pair_idx] = (
                    new_opponent_id,
                    player1_id,
                )

            # p1's original opponent (p1_orig_opp_id) now gets the bye
            self.rounds_byes_ids[round_index] = p1_orig_opp_id
        else:
            logging.error(
                f"Manual Adjust: New opponent {new_opp.name} not found in pairings or bye list for round {round_index+1}."
            )
            return False

        # Update previous_matches cautiously. Adding new ones is fine. Removing old ones might be too aggressive.
        self.previous_matches.add(frozenset({player1_id, new_opponent_id}))
        # If p1_orig_opp_id and new_opp_orig_opp_id were re-paired:
        if (
            p1_orig_opp_id and new_opp_orig_opp_id and new_opp_pair_idx != -1
        ):  # Check if they form a new pair
            # Only add if they are actually paired now, and were not the same player
            if p1_orig_opp_id != new_opp_orig_opp_id:
                self.previous_matches.add(
                    frozenset({p1_orig_opp_id, new_opp_orig_opp_id})
                )

        logging.warning(
            f"Manual Pairing Adjustment in Round {round_index+1}: {p1.name} now paired with {new_opp.name}. Other pairings potentially affected."
        )
        # Ensure self.rounds_pairings_ids[round_index] is updated with the modified list
        self.rounds_pairings_ids[round_index] = current_pairings_ids_for_round
        return True

    def set_manual_pairings(
        self,
        round_index: int,
        pairings: List[Tuple[Player, Player]],
        bye_player: Optional[Player],
    ) -> bool:
        """Set manual pairings for a specific round."""
        if round_index < 0:
            logging.error(f"Set Manual Pairings: Invalid round index {round_index}")
            return False

        # Ensure we have enough rounds
        while len(self.rounds_pairings_ids) <= round_index:
            self.rounds_pairings_ids.append([])

        while len(self.rounds_byes_ids) <= round_index:
            self.rounds_byes_ids.append(None)

        # Convert pairings to ID pairs
        pairings_ids = [(white.id, black.id) for white, black in pairings]
        bye_player_id = bye_player.id if bye_player else None

        # Update the round data
        self.rounds_pairings_ids[round_index] = pairings_ids
        self.rounds_byes_ids[round_index] = bye_player_id

        # Update previous matches to include these pairings
        for white, black in pairings:
            self.previous_matches.add(frozenset([white.id, black.id]))

        logging.info(
            f"Set manual pairings for round {round_index + 1}: {len(pairings)} pairings, bye: {bye_player.name if bye_player else 'None'}"
        )
        return True

    def record_results(
        self, round_index: int, results_data: List[Tuple[str, str, float]]
    ):
        """Record results, checking for active status and round index."""
        if round_index < 0 or round_index >= len(self.rounds_pairings_ids):
            logging.error(f"Record Results: Invalid round index {round_index}")
            return False

        round_pairings_ids = self.rounds_pairings_ids[round_index]
        round_bye_id = self.rounds_byes_ids[round_index]
        player_ids_in_pairings = {p_id for pair in round_pairings_ids for p_id in pair}
        processed_player_ids = set()
        success = True

        for white_id, black_id, white_score in results_data:
            p_white = self.players.get(white_id)
            p_black = self.players.get(black_id)

            if not (p_white and p_black):
                logging.error(
                    f"Record Results: Could not find players {white_id} or {black_id}."
                )
                success = False
                continue

            # Allow recording for inactive players but log warning.
            if not p_white.is_active:
                logging.warning(
                    f"Record Results: White player {p_white.name} is inactive."
                )
            if not p_black.is_active:
                logging.warning(
                    f"Record Results: Black player {p_black.name} is inactive."
                )

            # Check if result already recorded for this round for these players
            # This check needs to be robust. A player's result list grows by one each round.
            # If len(p_white.results) is already round_index + 1, it means result for this round_index is in.
            if len(p_white.results) > round_index or len(p_black.results) > round_index:
                logging.warning(
                    f"Record Results: Attempt to double-record for round {round_index+1}, players {white_id}/{black_id}. Current results len: W={len(p_white.results)}, B={len(p_black.results)}"
                )
                # This might allow re-recording if undo happened. The GUI should prevent double "Record & Advance" for same round.
                # Let's assume this is called once per round progression.
                # If a result for this round_index is already present, it implies an issue.
                # However, if undo occurred, results would be popped.
                # The current_round_index in main app tracks state.
                # This check might be too strict if we allow re-entering results for a non-advanced round.
                # For now, if results exist for this round_index, it's likely an issue.
                # Let's assume the GUI/workflow prevents re-recording if round already completed and advanced.
                # A better check: if this player's opponent_ids[round_index] is already set.
                if (
                    round_index < len(p_white.opponent_ids)
                    and p_white.opponent_ids[round_index] is not None
                    and p_white.opponent_ids[round_index] != black_id
                ):
                    logging.error(
                        f"Record Results: {p_white.name} already has opponent {p_white.opponent_ids[round_index]} for round {round_index+1}, not {black_id}"
                    )
                    success = False
                    continue

            black_score = WIN_SCORE - white_score
            p_white.add_round_result(opponent=p_black, result=white_score, color=W)
            p_black.add_round_result(opponent=p_white, result=black_score, color=B)
            processed_player_ids.add(white_id)
            processed_player_ids.add(black_id)
            logging.debug(
                f"Recorded result: {p_white.name} ({white_score}) vs {p_black.name} ({black_score})"
            )

        # Record bye result
        if round_bye_id:
            p_bye = self.players.get(round_bye_id)
            if p_bye:
                # Award bye score only if player is active *at the time of recording this round's results*
                # If player withdrew before this round started, they might not get the bye point.
                # Current logic: if p_bye.is_active. This is status *now*.
                # A player given a bye should generally get the point unless withdrawn *before* pairings.
                # This depends on tournament policy. USCF: usually bye stands if player withdraws after pairings.
                # For simplicity, if p_bye exists and is in rounds_byes_ids, they get point if active.

                if (
                    len(p_bye.results) == round_index
                ):  # Ensure not already recorded for this round
                    if p_bye.is_active:
                        p_bye.add_round_result(
                            opponent=None, result=BYE_SCORE, color=None
                        )
                        logging.debug(
                            f"Recorded bye (score {BYE_SCORE}) for active player {p_bye.name}"
                        )
                    else:
                        # If player is inactive, record a "bye received" but with 0 points.
                        # This marks them as having used their bye slot.
                        p_bye.add_round_result(opponent=None, result=0.0, color=None)
                        logging.debug(
                            f"Recorded bye (score 0.0) for inactive player {p_bye.name}. has_received_bye is now True."
                        )
                    processed_player_ids.add(round_bye_id)
                else:
                    logging.warning(
                        f"Record Results: Attempt to double-record bye for round {round_index+1} for {p_bye.name}. Results len: {len(p_bye.results)}"
                    )
                    # success = False # Don't mark as failure, but this is odd.
            else:
                logging.error(
                    f"Record Results: Could not find bye player ID {round_bye_id}."
                )
                success = False

        expected_ids = set(player_ids_in_pairings)
        if round_bye_id:
            expected_ids.add(round_bye_id)
        unprocessed = expected_ids - processed_player_ids
        if unprocessed:
            logging.warning(
                f"Record Results: Players/IDs in round {round_index + 1} not processed: {unprocessed}."
            )
        return success

    def compute_tiebreakers(self) -> None:
        # (No changes needed to this method based on the issues, assuming it's logically sound for its purpose)
        num_rounds_played = len(self.rounds_pairings_ids)
        if num_rounds_played == 0:
            return

        final_scores = {p.id: p.score for p in self.players.values()}
        ### ? ### final_scores is not used??
        player_dict = self.players

        for player in self.players.values():
            if (
                not player.is_active and not player.results
            ):  # Skip fully inactive players with no history
                player.tiebreakers = {}
                continue

            player.tiebreakers = {}
            opponents = player.get_opponent_objects(player_dict)
            actual_opponents = []
            opponent_final_scores = (
                []
            )  # Scores of opponents FOR TIEBREAK CALC (can differ from current live score)
            sb_score = 0.0
            cumulative_opp_score = 0.0

            for i, opp_obj in enumerate(opponents):
                if opp_obj is not None:  # Not a bye
                    actual_opponents.append(opp_obj)

                    # For tiebreaks like Solkoff/Median, use opponent's score.
                    # If opponent withdrew, their score is fixed at point of withdrawal for some systems,
                    # or their "final" score if tournament ended. Simpler: use current score.
                    # The original code's check for inactive opponent score seems reasonable:
                    # opp_final_score = (opp_obj.running_scores[-1] if opp_obj.running_scores and not opp_obj.is_active
                    #                    else self.players.get(opp_obj.id, opp_obj).score) # Fallback if opp_obj is a shallow copy
                    # Simpler and often used: just use the opponent's current total score.
                    opp_current_score = self.players[opp_obj.id].score
                    opponent_final_scores.append(opp_current_score)

                    result_against_opp = (
                        player.results[i] if i < len(player.results) else None
                    )
                    if result_against_opp is not None:
                        if result_against_opp == WIN_SCORE:
                            sb_score += opp_current_score
                        elif result_against_opp == DRAW_SCORE:
                            sb_score += 0.5 * opp_current_score

                    cumulative_opp_score += opp_current_score

            # --- True Modified Median ---
            # USCF: "Adjusted scores of opponents. For players with more than 50% score, drop lowest. For less than 50%, drop highest. For 50%, drop highest and lowest."
            # This applies to games played, not total rounds.
            num_games_played_by_player = len(
                [r for r in player.results if r is not None]
            )  # Count actual games, not byes
            ## ?? Also not used?

            # Median / Solkoff usually doesn't count unplayed games (e.g. forfeits by opponent after pairing) as 0 for opponent score.
            # Here, opponent_final_scores are scores of opponents they actually played.

            if opponent_final_scores:
                # Sort scores for median calculation
                sorted_opp_scores = sorted(
                    list(opponent_final_scores)
                )  # Make a copy for manipulation

                # For Median Buchholz variants, handling of unplayed games (e.g., if an opponent later forfeits unrelated games) can vary.
                # Here we use the actual scores of opponents faced.

                # USCF Median (Mod. Median or Harkness System for ties)
                # Rule 34E3. The Median System (Modified Median or Harkness System).
                # This is sum of opponents' scores, highest and lowest dropped if player's score is 50% of max possible for games played.
                # If player's score > 50% of max possible for games played, drop only lowest.
                # If player's score < 50% of max possible for games played, drop only highest.

                # Max possible score for games player *actually played* (excluding byes this player received)
                max_score_for_played_games = float(len(actual_opponents)) * WIN_SCORE

                # Player's score from *played games only* (excluding points from byes player received)
                score_from_played_games = sum(
                    player.results[i]
                    for i, opp_id in enumerate(player.opponent_ids)
                    if opp_id is not None and i < len(player.results)
                )

                if not actual_opponents:  # No games played against opponents
                    median_val = 0.0
                elif len(actual_opponents) == 1:  # Only one opponent
                    median_val = sum(
                        sorted_opp_scores
                    )  # effectively Solkoff for 1 game
                else:  # Multiple opponents
                    if (
                        max_score_for_played_games == 0
                    ):  # Avoid division by zero if no games played somehow
                        median_val = sum(sorted_opp_scores)
                    elif score_from_played_games > max_score_for_played_games / 2.0:
                        median_val = sum(sorted_opp_scores[1:])  # Drop lowest
                    elif score_from_played_games < max_score_for_played_games / 2.0:
                        median_val = sum(sorted_opp_scores[:-1])  # Drop highest
                    else:  # Exactly 50%
                        if (
                            len(sorted_opp_scores) >= 2
                        ):  # Need at least 2 scores to drop both
                            median_val = sum(
                                sorted_opp_scores[1:-1]
                            )  # Drop highest and lowest
                        else:  # Only one score, cannot drop two. Or if only 2 scores, sum is 0.
                            median_val = sum(
                                sorted_opp_scores
                            )  # Or 0 if only 1-2 opps and 50% score. Sum is fine.
            else:
                median_val = 0.0

            player.tiebreakers[TB_MEDIAN] = median_val
            player.tiebreakers[TB_SOLKOFF] = sum(
                opponent_final_scores
            )  # Sum of all opponents' scores
            player.tiebreakers[TB_CUMULATIVE] = (
                sum(player.running_scores) if player.running_scores else 0.0
            )
            player.tiebreakers[TB_CUMULATIVE_OPP] = (
                cumulative_opp_score  # This is also Solkoff if calculated simply
            )
            player.tiebreakers[TB_SONNENBORN_BERGER] = sb_score
            player.tiebreakers[TB_MOST_BLACKS] = float(player.num_black_games)
            player.tiebreakers[TB_HEAD_TO_HEAD] = (
                0.0  # Needs specific calculation logic if used directly
            )

    def _compare_players(self, p1: Player, p2: Player) -> int:
        # (No changes needed here based on issues)
        if p1.score != p2.score:
            return 1 if p1.score > p2.score else -1
        h2h_score_p1_vs_p2 = 0.0
        p1_won_h2h = False
        p2_won_h2h = False

        for i, opp_id in enumerate(p1.opponent_ids):
            if opp_id == p2.id and i < len(p1.results):
                result = p1.results[i]
                if result == WIN_SCORE:
                    p1_won_h2h = True
                elif result == LOSS_SCORE:
                    p2_won_h2h = True

        if p1_won_h2h and not p2_won_h2h:
            return 1  # p1 beat p2
        if p2_won_h2h and not p1_won_h2h:
            return -1  # p2 beat p1

        for tb_key in self.tiebreak_order:
            tb1 = p1.tiebreakers.get(tb_key, 0.0)
            tb2 = p2.tiebreakers.get(tb_key, 0.0)
            if tb1 != tb2:
                return 1 if tb1 > tb2 else -1
        if p1.rating != p2.rating:
            return 1 if p1.rating > p2.rating else -1
        if p1.name != p2.name:
            return -1 if p1.name < p2.name else 1
        return 0

    def get_standings(self) -> List[Player]:
        """Get the current standings of the Tournament.

        Returns
        -------
        List[Player]
            [0] being leader of tournament, [1] being 2nd, ...
        """
        # Active players are typically shown first, then inactive ones, or inactive are hidden.
        # Current _get_active_players() filters out inactive ones. This is fine for standings.
        players_for_standings = self._get_active_players()
        # If you want to show inactive players at the bottom:
        # players_for_standings = list(self.players.values())
        # players_for_standings.sort(key=lambda p: not p.is_active) # Active players first

        if not players_for_standings:
            return []
        self.compute_tiebreakers()

        # Sort primarily by active status (active first), then score, then tiebreaks
        # However, get_standings is usually for ranked list of those still competing.
        # If inactive players are included, they usually appear after active ones with same score.
        # The _compare_players doesn't consider p.is_active.
        # For now, assuming get_standings is for active players.

        sorted_players = sorted(
            players_for_standings,  # Only active ones
            key=functools.cmp_to_key(self._compare_players),
            reverse=True,
        )
        return sorted_players

    def get_completed_rounds(self) -> int:
        # (No changes needed here)
        active_players = self._get_active_players()
        if not active_players:
            return 0
        players_with_results = [p for p in active_players if p.results]
        if not players_with_results:
            return 0
        # This should be min length of results for players who are *still active* and *have results*.
        # A player who withdrew in R1 (is_active=False) might have 1 result.
        # A player still active might have played 3 rounds. Min should be 3.
        # If all players withdrew after R1, completed_rounds is 1.
        # If some are active with 3 results, some active with 2 (late entry?), this is tricky.
        # "Completed rounds" usually means rounds for which *all* results of *scheduled* games are in.
        # The current_round_index in GambitPairingMainWindow is a better indicator of *processed* rounds.
        # This method is okay as an approximation.
        return min(len(p.results) for p in players_with_results)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the tournament state to a dictionary."""
        # TODO: Document
        return {
            "name": self.name,
            "players": [p.to_dict() for p in self.players.values()],
            "num_rounds": self.num_rounds,
            "tiebreak_order": self.tiebreak_order,
            "rounds_pairings_ids": self.rounds_pairings_ids,
            "rounds_byes_ids": self.rounds_byes_ids,
            "previous_matches": [list(pair) for pair in self.previous_matches],
            "manual_pairings": self.manual_pairings,
            "pairing_system": self.pairing_system,  # NEW: serialize pairing system
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tournament":
        """Deserialize a tournament from a dictionary."""
        # TODO document expected Dict parameters
        players = [Player.from_dict(p_data) for p_data in data["players"]]
        num_rounds = data["num_rounds"]

        # Handle legacy files that may not have a name
        name = data.get("name", "Untitled Tournament")

        pairing_system = data.get(
            "pairing_system", "dutch_swiss"
        )  # NEW: load pairing system
        tourney = cls(name, players, num_rounds, pairing_system=pairing_system)
        tourney.tiebreak_order = data.get(
            "tiebreak_order", list(DEFAULT_TIEBREAK_SORT_ORDER)
        )
        tourney.rounds_pairings_ids = [
            tuple(map(tuple, r)) for r in data.get("rounds_pairings_ids", [])
        ]
        tourney.rounds_byes_ids = data.get("rounds_byes_ids", [])
        tourney.previous_matches = set(
            frozenset(map(str, pair)) for pair in data.get("previous_matches", [])
        )  # Ensure IDs are str

        # Convert round keys in manual_pairings back to int
        raw_manual_pairings = data.get("manual_pairings", {})
        tourney.manual_pairings = {int(k): v for k, v in raw_manual_pairings.items()}

        for p in tourney.players.values():
            p._opponents_played_cache = []
        return tourney


#  LocalWords:  swiss RoundRobin
