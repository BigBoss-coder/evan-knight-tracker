#!/usr/bin/env python3
"""
Round-complete notification tracker for Evan Knight.

The script reads PGA TOUR's page payload, finds Evan's leaderboard row, and
sends one Telegram alert when a round changes to complete.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_LEADERBOARD_URLS = ["https://www.pgatour.com/americas/leaderboard"]
DEFAULT_PLAYER_PAGE = "https://www.pgatour.com/americas/player/56731/evan-knight"
STATE_PATH = Path(os.getenv("STATE_PATH", "state/evan_knight_state.json"))


@dataclass
class PlayerRound:
    source_url: str
    tournament_id: str
    tournament_name: str
    tournament_location: str
    tournament_dates: str
    round_label: str
    current_round: str
    position: str
    total: str
    today: str
    thru: str
    status: str
    round_scores: list[str]
    movement: str
    leader: str
    leaderboard_url: str

    @property
    def alert_key(self) -> str:
        return f"{self.tournament_id}:round:{self.current_round}:complete"

    @property
    def is_complete(self) -> bool:
        thru = clean(self.thru).upper().replace("*", "")
        status = clean(self.status).upper()
        return thru == "F" or "COMPLETE" in status


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clean(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def fetch(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_next_data(html: str) -> dict[str, Any]:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ payload")
    return json.loads(match.group(1))


def get_queries(next_data: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("dehydratedState", {})
        .get("queries", [])
    )


def query_data(query: dict[str, Any]) -> Any:
    return query.get("state", {}).get("data")


def get_tournaments(queries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    tournaments: dict[str, dict[str, Any]] = {}
    for query in queries:
        data = query_data(query)
        if isinstance(data, dict) and data.get("id") and data.get("tournamentName"):
            tournaments[data["id"]] = data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id") and item.get("tournamentName"):
                    tournaments[item["id"]] = item
    return tournaments


def find_leaderboard_rounds(
    url: str,
    next_data: dict[str, Any],
    player_id: str,
) -> list[PlayerRound]:
    queries = get_queries(next_data)
    tournaments = get_tournaments(queries)
    rounds: list[PlayerRound] = []

    for query in queries:
        data = query_data(query)
        if not isinstance(data, dict):
            continue
        players = data.get("players")
        if not isinstance(players, list):
            continue
        if not any(isinstance(player, dict) and isinstance(player.get("scoringData"), dict) for player in players):
            continue

        tournament_id = clean(data.get("tournamentId") or data.get("id"), "unknown")
        tournament = tournaments.get(tournament_id, {})
        leader = format_leader(players)

        for player_row in players:
            if not isinstance(player_row, dict):
                continue
            if clean(player_row.get("id") or player_row.get("playerId")) != player_id:
                continue
            scoring = player_row.get("scoringData", {})
            if not isinstance(scoring, dict):
                scoring = {}

            round_number = clean(scoring.get("currentRound") or tournament.get("currentRound"))
            round_label = clean(scoring.get("roundHeader") or data.get("leaderboardRoundHeader") or tournament.get("roundDisplay"))
            rounds.append(
                PlayerRound(
                    source_url=url,
                    tournament_id=tournament_id,
                    tournament_name=clean(tournament.get("tournamentName") or data.get("tournamentName")),
                    tournament_location=clean(tournament.get("tournamentLocation") or tournament.get("city")),
                    tournament_dates=clean(tournament.get("displayDate")),
                    round_label=round_label,
                    current_round=round_number,
                    position=clean(scoring.get("position")),
                    total=clean(scoring.get("total")),
                    today=clean(scoring.get("score")),
                    thru=clean(scoring.get("thru")),
                    status=clean(scoring.get("roundStatus") or scoring.get("playerState")),
                    round_scores=[clean(score) for score in scoring.get("rounds", [])],
                    movement=format_movement(scoring),
                    leader=leader,
                    leaderboard_url=url,
                )
            )
    return rounds


def find_profile_status_round(
    url: str,
    next_data: dict[str, Any],
    player_id: str,
) -> PlayerRound | None:
    queries = get_queries(next_data)
    tournaments = get_tournaments(queries)
    for query in queries:
        key = query.get("queryKey", [])
        data = query_data(query)
        if not isinstance(data, dict):
            continue
        if not (isinstance(key, list) and key and key[0] == "playerProfileTournamentStatus"):
            continue
        if clean(data.get("playerId")) != player_id:
            continue

        tournament_id = clean(data.get("tournamentId"), "unknown")
        tournament = tournaments.get(tournament_id, {})
        round_label = clean(data.get("roundDisplay"))
        current_round = re.sub(r"\D+", "", round_label) or clean(tournament.get("currentRound"))
        return PlayerRound(
            source_url=url,
            tournament_id=tournament_id,
            tournament_name=clean(data.get("tournamentName") or tournament.get("tournamentName")),
            tournament_location=clean(tournament.get("tournamentLocation") or tournament.get("city")),
            tournament_dates=clean(tournament.get("displayDate")),
            round_label=round_label,
            current_round=current_round,
            position=clean(data.get("position")),
            total=clean(data.get("total")),
            today=clean(data.get("score")),
            thru=clean(data.get("thru")),
            status=clean(data.get("roundStatusDisplay") or data.get("displayMode")),
            round_scores=[],
            movement="-",
            leader="-",
            leaderboard_url=url,
        )
    return None


def format_leader(players: list[dict[str, Any]]) -> str:
    if not players:
        return "-"
    first = players[0]
    if not isinstance(first, dict):
        return "-"
    player = first.get("player", {})
    if not isinstance(player, dict):
        player = {}
    scoring = first.get("scoringData", {})
    if not isinstance(scoring, dict):
        scoring = {}
    name = clean(player.get("displayName") or first.get("playerName"))
    total = clean(scoring.get("total"))
    position = clean(scoring.get("position"))
    return f"{position} {name} ({total})"


def format_movement(scoring: dict[str, Any]) -> str:
    direction = clean(scoring.get("movementDirection"), "")
    amount = clean(scoring.get("movementAmount"), "")
    if not direction or direction == "-":
        return "-"
    if direction.upper() == "SAME":
        return "No change"
    return f"{direction.title()} {amount}".strip()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"sent_alerts": {}, "last_seen": {}}
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {"sent_alerts": {}, "last_seen": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def build_message(player_name: str, result: PlayerRound) -> str:
    scores = ", ".join(result.round_scores) if result.round_scores else "-"
    lines = [
        f"{player_name} round complete",
        "",
        result.tournament_name,
        f"{result.round_label}: {result.today} today",
        f"Position: {result.position}",
        f"Total: {result.total}",
        f"Thru: {result.thru}",
        f"Round scores: {scores}",
    ]
    if result.movement != "-":
        lines.append(f"Movement: {result.movement}")
    if result.leader != "-":
        lines.append(f"Leader: {result.leader}")
    if result.tournament_location != "-":
        lines.append(f"Location: {result.tournament_location}")
    if result.tournament_dates != "-":
        lines.append(f"Dates: {result.tournament_dates}")
    lines.extend(["", result.leaderboard_url])
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    dry_run = env_bool("DRY_RUN", False)

    if dry_run or not token or not chat_id:
        print("Notification preview:\n")
        print(message)
        if not token or not chat_id:
            print("\nTelegram token/chat ID not set, so no message was sent.")
        return False

    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    request = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram send failed: {body}")
    return True


def configured_urls() -> list[str]:
    urls = list(DEFAULT_LEADERBOARD_URLS)
    extra = os.getenv("EXTRA_LEADERBOARD_URLS", "")
    for url in extra.split(","):
        url = url.strip()
        if url:
            urls.append(url)
    return list(dict.fromkeys(urls))


def collect_results(player_id: str) -> list[PlayerRound]:
    results: list[PlayerRound] = []
    errors: list[str] = []

    for url in configured_urls():
        try:
            next_data = parse_next_data(fetch(url))
            results.extend(find_leaderboard_rounds(url, next_data, player_id))
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{url}: {exc}")

    if not results:
        try:
            next_data = parse_next_data(fetch(os.getenv("PLAYER_PAGE_URL", DEFAULT_PLAYER_PAGE)))
            profile_result = find_profile_status_round(DEFAULT_PLAYER_PAGE, next_data, player_id)
            if profile_result:
                results.append(profile_result)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{DEFAULT_PLAYER_PAGE}: {exc}")

    for error in errors:
        print(f"Source warning: {error}", file=sys.stderr)
    return results


def main() -> int:
    player_id = os.getenv("PLAYER_ID", "56731").strip()
    player_name = os.getenv("PLAYER_NAME", "Evan Knight").strip()
    round_complete_only = env_bool("ROUND_COMPLETE_ONLY", True)

    state = load_state()
    state.setdefault("sent_alerts", {})
    state.setdefault("last_seen", {})

    results = collect_results(player_id)
    if not results:
        print(f"No active leaderboard row found for {player_name}.")
        state["last_checked_at"] = int(time.time())
        save_state(state)
        return 0

    sent_count = 0
    for result in results:
        state["last_seen"][result.tournament_id] = {
            "tournament_name": result.tournament_name,
            "round": result.current_round,
            "position": result.position,
            "today": result.today,
            "total": result.total,
            "thru": result.thru,
            "status": result.status,
            "seen_at": int(time.time()),
        }

        if round_complete_only and not result.is_complete:
            print(
                f"{player_name} is in {result.tournament_name}, "
                f"but {result.round_label} is not complete yet ({result.thru})."
            )
            continue

        if result.alert_key in state["sent_alerts"]:
            print(f"Already sent alert for {result.tournament_name} {result.round_label}.")
            continue

        message = build_message(player_name, result)
        delivered = send_telegram(message)
        if delivered:
            state["sent_alerts"][result.alert_key] = {
                "sent_at": int(time.time()),
                "tournament_name": result.tournament_name,
                "round": result.current_round,
                "position": result.position,
                "today": result.today,
                "total": result.total,
            }
            sent_count += 1
        else:
            print("Alert was not recorded as sent because no notification was delivered.")

    state["last_checked_at"] = int(time.time())
    save_state(state)
    print(f"Done. Sent {sent_count} notification(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
