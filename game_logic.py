"""
Ойынның негізгі логикасы: ойыншыларды қосу, рөлдерді тарату,
дауыс беруді есептеу және жеңіс шартын тексеру.

Бұл модуль Telegram API-мен тікелей жұмыс істемейді — тек таза деректермен
(game dict) жұмыс істейді, сондықтан оны тестілеу және кеңейту оңай.
"""

import random
import string
from typing import Dict, List, Optional, Tuple

from config import MIN_PLAYERS
from database import storage


def generate_game_id() -> str:
    """Бірегей ойын идентификаторын жасайды (мыс. GAME_A1B2C3)."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"GAME_{suffix}"


def add_player(game_id: str, user_id: int, name: str) -> bool:
    """
    Ойыншыны ойынға қосады.
    Ойын табылмаса немесе ойын қазірдің өзінде басталған болса, False қайтарады.
    """
    game = storage.get_game(game_id)
    if not game or game["status"] != "waiting":
        return False

    uid = str(user_id)
    if uid not in game["players"]:
        game["players"][uid] = {
            "name": name,
            "alive": True,
            "role": None,
            "word": None,
        }
        storage.update_game(game_id, game)

    storage.set_user_game(user_id, game_id)
    return True


def get_players_list_text(game: dict) -> str:
    """Ойыншылар тізімін админге көрсету үшін мәтінге айналдырады."""
    players = list(game["players"].values())
    if not players:
        body = "Әзірге ешкім қосылған жоқ."
    else:
        body = "\n".join(f"{i + 1}. {p['name']}" for i, p in enumerate(players))
    return f"Ойыншылар ({len(players)}):\n\n{body}\n\nБарлығы: {len(players)}"


def has_enough_players(game: dict) -> bool:
    """Ойынды бастауға жеткілікті ойыншы бар-жоғын тексереді."""
    return len(game["players"]) >= MIN_PLAYERS


def assign_roles_and_word(game: dict, spy_count: int, word: str) -> None:
    """
    Рөлдерді (шпион/бейбіт) және құпия сөзді кездейсоқ таратады.
    Бұл әр ойында тек бір рет — бірінші раунд басталғанда шақырылады.
    """
    player_ids = list(game["players"].keys())
    spy_count = max(1, min(spy_count, len(player_ids) - 1))
    spies = random.sample(player_ids, spy_count)

    for uid, pdata in game["players"].items():
        pdata["alive"] = True
        if uid in spies:
            pdata["role"] = "spy"
            pdata["word"] = None
        else:
            pdata["role"] = "civilian"
            pdata["word"] = word

    game["spies"] = spies
    game["word"] = word
    game["spy_count"] = spy_count
    game["status"] = "playing"
    game["votes"] = {}
    game["tie_candidates"] = []
    game["roles_assigned"] = True


def get_alive_players(game: dict) -> List[Tuple[str, dict]]:
    """Тірі қалған ойыншылардың (user_id_str, player_data) тізімін қайтарады."""
    return [(uid, p) for uid, p in game["players"].items() if p["alive"]]


def register_vote(game: dict, voter_id: int, target_id: int) -> bool:
    """
    Дауысты тіркейді. Ойыншы бір рет қана дауыс бере алады және оны өзгерте алмайды,
    сондықтан бұрын дауыс берген болса False қайтарады.
    """
    voter = str(voter_id)
    target = str(target_id)
    if voter in game["votes"]:
        return False
    game["votes"][voter] = target
    return True


def all_alive_have_voted(game: dict) -> bool:
    """Барлық тірі ойыншы дауыс бергенін тексереді."""
    alive_ids = {uid for uid, p in game["players"].items() if p["alive"]}
    return alive_ids.issubset(set(game["votes"].keys()))


def tally_votes(game: dict) -> Tuple[Dict[str, int], List[str], int]:
    """
    Дауыстарды санайды.
    Қайтарады: (әр ойыншыға берілген дауыс саны, ең көп дауыс алғандар тізімі, максимум дауыс саны)
    """
    counts: Dict[str, int] = {}
    for target in game["votes"].values():
        counts[target] = counts.get(target, 0) + 1

    if not counts:
        return counts, [], 0

    max_votes = max(counts.values())
    top = [uid for uid, c in counts.items() if c == max_votes]
    return counts, top, max_votes


def eliminate_player(game: dict, user_id_str: str) -> None:
    """Ойыншыны ойыннан шығарады (өлі деп белгілейді)."""
    if user_id_str in game["players"]:
        game["players"][user_id_str]["alive"] = False


def check_win_condition(game: dict) -> Optional[str]:
    """
    Жеңіс шартын тексереді.
    'civilians' — барлық шпиондар шығарылды, бейбіт ойыншылар жеңді.
    'spies'     — шпион саны бейбіттермен теңесті немесе асып түсті, шпиондар жеңді.
    None        — ойын жалғасады.
    """
    alive = [p for p in game["players"].values() if p["alive"]]
    alive_spies = [p for p in alive if p["role"] == "spy"]
    alive_civilians = [p for p in alive if p["role"] == "civilian"]

    if len(alive_spies) == 0:
        return "civilians"
    if len(alive_spies) >= len(alive_civilians):
        return "spies"
    return None


def start_new_round(game: dict, new_word: str) -> None:
    """
    Жаңа раундты бастайды: шпиондар өзгермейді, тек жаңа сөз тірі бейбіт
    ойыншыларға таратылады.
    """
    game["round"] += 1
    game["votes"] = {}
    game["tie_candidates"] = []
    game["status"] = "playing"
    game["word"] = new_word

    for pdata in game["players"].values():
        if pdata["alive"] and pdata["role"] == "civilian":
            pdata["word"] = new_word
