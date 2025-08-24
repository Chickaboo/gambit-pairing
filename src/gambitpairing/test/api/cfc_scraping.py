from typing import List

import httpx

from gambitpairing.player import CfcPlayer

BASE_URL = "https://www.chess.ca/api"


def _parse_player(data: dict) -> "Player":
    """Convert a raw API player record into a Player instance."""
    return Player(
        name=data.get("name", ""),
        city=data.get("city", ""),
        cfc_id=str(data.get("id", "")),
        expiry=data.get("membership_expiry", ""),
        regular_rating=str(data.get("regular_rating", "")),
        quick_rating=str(data.get("quick_rating", "")),
    )


def search_players_by_name(name: str, timeout: float = 10.0) -> "PlayerList":
    """
    Search for players by name using the CFC API.

    Parameters
    ----------
    name : str
        The player's name or part of it.
    timeout : float, optional
        Timeout in seconds (default 10).

    Returns
    -------
    PlayerList
        A list-like container of `Player` objects.

    Raises
    ------
    httpx.RequestError
        If there is a network problem.
    httpx.HTTPStatusError
        If the server responds with an HTTP error status.
    """
    url = f"{BASE_URL}/search/player"
    headers = {"User-Agent": "CFC-Search/1.0"}
    params = {"name": name}

    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        results = response.json()

    return PlayerList([_parse_player(player_data) for player_data in results])
