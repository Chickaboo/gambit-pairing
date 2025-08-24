"""Utilities for talking with CFC web endpoints.

Provides helper functions to retrieve player information from
API/website via HTTP requests and BeautifulSoup parsing.
"""

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
import re
import urllib.parse
from typing import List

import httpx
from bs4 import BeautifulSoup

from gambitpairing.player import Player
from gambitpairing.utils import setup_logger

logger = setup_logger(__name__)

from typing import List

FLAG_RE = re.compile(r"/images/flags/([a-zA-Z]{2})\.svg(?:\?|$)", re.IGNORECASE)
# URL stubs for API endpoints
CFC_URL = "https://www.chess.ca/"
CFC_RATINGS_URL = "https://www.chess.ca/en/ratings/"


def _parse_player(data: dict) -> "Player":
    """Convert a raw API player record into a Player instance."""
    return dict(
        name=data.get("name", ""),
        city=data.get("city", ""),
        cfc_id=str(data.get("id", "")),
        expiry=data.get("membership_expiry", ""),
        regular_rating=str(data.get("regular_rating", "")),
        quick_rating=str(data.get("quick_rating", "")),
    )


def search_players_by_name(
    first_name: str, last_name: str, timeout: float = 10.0
) -> "PlayerList":
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
    url = f"{CFC_RATINGS_URL}p/sr/?fn={first_name}&ln={last_name}"
    headers = {"User-Agent": "CFC-Search/1.0"}
    params = {"name": name}

    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        results = response.json()

    return [_parse_player(player_data) for player_data in results]


def get_cfc_player_info(cfc_id: str):
    """Retrieve player information from CFC API.

    Gets player details including name, rating and membership status
    from the Chess Federation of Canada API.

    Parameters
    ----------
    cfc_id : str
        The CFC ID number of the player to look up.

    Returns
    -------
    dict - JSON response from the API.
        example:
        {'updated': '2025-04-24',
        'player': {
            'cfc_id': 123123,
            'cfc_expiry': '2020-01-02',
            'fide_id': 0,
            'name_first': 'Michael',
            'name_last': 'Williams',
            'addr_city': "St.John's",
            'addr_province': 'NL',
            'regular_rating': 200,
            'regular_indicator': 11,
            'quick_rating': 200,
            'quick_indicator': 11,
            'events': [{'id': 199806005,
                'name': 'MacDonald Dr RR',
                'date_end': '1998-05-14',
                'rating_type': 'R',
                'games_played': 11,
                'score': 0.0,
                'rating_pre': 0,
                'rating_perf': 0,
                'rating_post': 200,
                'rating_indicator': 11}],
            'orgarb': [],
            'is_organizer': False,
            'is_arbiter': False
        },
        'apicode': 0,
        'error': ''}

        Player information from the API response.
        Contains fields like name, rating, expiry date, etc.

    Raises
    ------
    httpx.exceptions.RequestException
        If the API request fails for any reason
    ValueError
        If the response is not valid JSON
    """
    api_path = f"/api/player/v1/{cfc_id}"

    try:
        r = httpx.get(CFC_URL_STUB + api_path)
        r.raise_for_status()

        api_info = r.json()
        logger.debug("CFC API response: %s", api_info)

        if "name_last" not in api_info["player"]:
            raise ValueError(f"{api_path} did not return a player")

        return api_info["player"]

    except httpx.HTTPError as e:
        raise httpx.HTTPError(f"HTTP error: {e}")


def build_cfc_url(cfc_id=None, first_name=None, last_name=None):
    """Build the search URL for the CFC ratings page. Does not use api.

    Parameters
    ----------
    cfc_id : str, optional
        The player's CFC ID.
    first_name : str, optional
        The player's first name (supports wildcards, e.g., "Bob*").
    last_name : str, optional
        The player's last name (supports wildcards, e.g., "Fis*er").

    Returns
    -------
    str
        The fully constructed URL for the query.
    """
    params = {}
    if cfc_id:
        params["id"] = cfc_id
    else:
        if first_name:
            params["fn"] = first_name
        if last_name:
            params["ln"] = last_name
    query = "&".join(
        f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}"
        for k, v in params.items()
    )
    return f"{CFC_RATINGS_URL}p/sr/?{query}"


def parse_cfc_results(html: str) -> List[dict]:
    """Parse the HTML response from the CFC ratings page.

    Parameters
    ----------
    html : str
        The raw HTML content of the response.

    Returns
    -------
    list of dict
        A list of dictionaries, where each dictionary represents a player with:
        - "Name": str
        - "City": str
        - "CFC ID": str
        - "Expiry": str
        - "Regular Rating": str
        - "Quick Rating": str
    """
    soup = BeautifulSoup(html, "html.parser")
    players = soup.select("table tr")[1:]  # skip header

    results = []
    for player in players:
        cols = [c.get_text(strip=True) for c in player.find_all("td")]
        if len(cols) < 6:
            # if there are more than six columns, it is not a player
            continue
        results.append(
            {
                "Name": cols[0],
                "City": cols[1],
                "CFC ID": cols[2],
                "Expiry": cols[3],
                "Regular Rating": cols[4],
                "Quick Rating": cols[5],
            }
        )
    return results


def search_cfc(cfc_id=None, first_name=None, last_name=None, timeout=10.0):
    """Search for a player in the CFC ratings database.

    Parameters
    ----------
    cfc_id : str, optional
        The player's CFC ID. If provided, `first_name` and `last_name` are ignored.
    first_name : str, optional
        The player's first name (supports wildcards).
    last_name : str, optional
        The player's last name (supports wildcards).
    timeout : float, default=10.0
        Timeout in seconds for the HTTP request.

    Returns
    -------
    list of dict
        A list of player dictionaries containing player details.

    Raises
    ------
    httpx.RequestError
        If there is a network-related issue.
    httpx.HTTPStatusError
        If the server responds with an HTTP error status.
    """
    url = build_cfc_url(cfc_id, first_name, last_name)
    logger.info("api.search_cfc: Querying: {%s}", url)

    with httpx.Client(
        timeout=timeout, headers={"User-Agent": "CFC-Search/1.0"}
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        res = parse_cfc_results(resp.text)
        logger.debug("httpx response: %s", res)
        return res


def build_cfc_url(cfc_id=None, first_name=None, last_name=None):
    """Build the search URL for the CFC ratings page. Does not use api.

    Parameters
    ----------
    cfc_id : str, optional
        The player's CFC ID.
    first_name : str, optional
        The player's first name (supports wildcards, e.g., "Bob*").
    last_name : str, optional
        The player's last name (supports wildcards, e.g., "Fis*er").

    Returns
    -------
    str
        The fully constructed URL for the query.
    """
    params = {}
    if cfc_id:
        params["id"] = cfc_id
    else:
        if first_name:
            params["First name"] = first_name
        if last_name:
            params["Last name"] = last_name
    query = "&".join(
        f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}"
        for k, v in params.items()
    )
    return f"{CFC_RATINGS_URL}?{query}"


def parse_cfc_results(html: str) -> List[dict]:
    """Parse the HTML response from the CFC ratings page.

    Parameters
    ----------
    html : str
        The raw HTML content of the response.

    Returns
    -------
    list of dict
        A list of dictionaries, where each dictionary represents a player with:
        - "Name": str
        - "City": str
        - "CFC ID": str
        - "Expiry": str
        - "Regular Rating": str
        - "Quick Rating": str
    """
    soup = BeautifulSoup(html, "html.parser")
    players = soup.select("table tr")[1:]  # skip header

    results = []
    for player in players:
        cols = [c.get_text(strip=True) for c in player.find_all("td")]
        if len(cols) < 6:
            # if there are more than six columns, it is not a player
            continue
        results.append(
            {
                "Name": cols[0],
                "City": cols[1],
                "CFC ID": cols[2],
                "Expiry": cols[3],
                "Regular Rating": cols[4],
                "Quick Rating": cols[5],
            }
        )
    return results


def search_cfc(cfc_id=None, first_name=None, last_name=None, timeout=10.0):
    """Search for a player in the CFC ratings database.

    Parameters
    ----------
    cfc_id : str, optional
        The player's CFC ID. If provided, `first_name` and `last_name` are ignored.
    first_name : str, optional
        The player's first name (supports wildcards).
    last_name : str, optional
        The player's last name (supports wildcards).
    timeout : float, default=10.0
        Timeout in seconds for the HTTP request.

    Returns
    -------
    list of dict
        A list of player dictionaries containing player details.

    Raises
    ------
    httpx.RequestError
        If there is a network-related issue.
    httpx.HTTPStatusError
        If the server responds with an HTTP error status.
    """
    url = build_cfc_url(cfc_id, first_name, last_name)
    logger.info("api.search_cfc: Querying: {%s}", url)

    with httpx.Client(
        timeout=timeout, headers={"User-Agent": "CFC-Search/1.0"}
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        res = parse_cfc_results(resp.text)
        logger.debug("httpx response: %s", res)
        return res
