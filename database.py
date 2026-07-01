"""
Ойын деректерін JSON файлында сақтайтын модуль.

Барлық ойындар бір JSON файлында сақталады, сондықтан бот қайта қосылса да
(қайта іске қосылса да) белсенді ойындар жоғалмайды. Бір уақытта бірнеше
тәуелсіз ойын жұмыс істей алады, себебі әр ойын өзінің бірегей game_id
кілтімен сақталады.
"""

import json
import os
import threading
from typing import Any, Dict, Optional

from config import DATA_FILE


class GameStorage:
    """Ойындарды және ойыншы-ойын байланысын сақтайтын класс."""

    def __init__(self, filepath: str = DATA_FILE):
        self.filepath = filepath
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {"games": {}, "user_game_map": {}}
        self._load()

    def _load(self) -> None:
        """Деректерді файлдан оқиды. Файл жоқ немесе бүлінген болса, бос базадан бастайды."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                self._data.setdefault("games", {})
                self._data.setdefault("user_game_map", {})
            except (json.JSONDecodeError, IOError):
                self._data = {"games": {}, "user_game_map": {}}
        else:
            self._save()

    def _save(self) -> None:
        """Деректерді файлға жазады."""
        with self._lock:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Ойын операциялары
    # ------------------------------------------------------------------

    def create_game(self, game_id: str, admin_id: int) -> dict:
        """Жаңа ойын жазбасын жасайды және сақтайды."""
        game = {
            "admin_id": admin_id,
            "status": "waiting",  # waiting -> choosing_spy_count -> entering_word ->
                                   # playing -> voting -> revote -> round_end_decision -> finished
            "players": {},          # {user_id_str: {name, alive, role, word}}
            "spy_count": None,
            "word": None,
            "spies": [],             # шпион болған ойыншылардың user_id_str тізімі
            "round": 1,
            "votes": {},             # {voter_id_str: target_id_str}
            "tie_candidates": [],
            "roles_assigned": False,  # рөлдер бір рет қана таратылады, содан кейін тек сөз ауысады
        }
        self._data["games"][game_id] = game
        self._save()
        return game

    def get_game(self, game_id: str) -> Optional[dict]:
        return self._data["games"].get(game_id)

    def update_game(self, game_id: str, game: dict) -> None:
        self._data["games"][game_id] = game
        self._save()

    def delete_game(self, game_id: str) -> None:
        game = self._data["games"].pop(game_id, None)
        if game:
            for uid in list(game.get("players", {}).keys()):
                self._data["user_game_map"].pop(uid, None)
        self._save()

    def get_admin_games(self, admin_id: int) -> Dict[str, dict]:
        """Осы админге тиесілі барлық ойындарды қайтарады (аяқталғандарды қоса)."""
        return {
            gid: g
            for gid, g in self._data["games"].items()
            if g["admin_id"] == admin_id
        }

    # ------------------------------------------------------------------
    # Ойыншы <-> ойын байланысы
    # ------------------------------------------------------------------

    def set_user_game(self, user_id: int, game_id: str) -> None:
        self._data["user_game_map"][str(user_id)] = game_id
        self._save()

    def get_user_game_id(self, user_id: int) -> Optional[str]:
        return self._data["user_game_map"].get(str(user_id))

    def remove_user_game(self, user_id: int) -> None:
        self._data["user_game_map"].pop(str(user_id), None)
        self._save()


# Бүкіл бот бойынша қолданылатын жалғыз (singleton) сақтау нысаны
storage = GameStorage()
