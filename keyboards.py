"""
Ботта қолданылатын барлық InlineKeyboard түймелерін жасайтын модуль.
"""

from typing import List, Tuple

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MAX_SPIES


def start_game_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Ойынды бастау және тізімді жаңарту батырмалары (тек әкімге арналған)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Ойынды бастау", callback_data=f"startgame:{game_id}")
    builder.button(text="🔄 Тізімді жаңарту", callback_data=f"refresh:{game_id}")
    builder.adjust(1)
    return builder.as_markup()


def spy_count_keyboard(game_id: str, player_count: int) -> InlineKeyboardMarkup:
    """Шпион санын таңдау үшін 1-ден бастап батырмалар тізімі."""
    builder = InlineKeyboardBuilder()
    max_spies = max(1, min(player_count - 1, MAX_SPIES))
    for n in range(1, max_spies + 1):
        builder.button(text=str(n), callback_data=f"spycount:{game_id}:{n}")
    builder.adjust(5)
    return builder.as_markup()


def vote_button_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Жүргізушіге дауыс беруді бастау батырмасы."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗳 Дауыс беру", callback_data=f"vote_start:{game_id}")
    builder.adjust(1)
    return builder.as_markup()


def voting_targets_keyboard(
    game_id: str, candidates: List[Tuple[str, dict]], voter_id: int
) -> InlineKeyboardMarkup:
    """
    Ойыншыға дауыс беру үшін нысандар тізімін көрсетеді.
    Өзіне дауыс бере алмайтындықтан, өзін тізімнен алып тастайды.
    """
    builder = InlineKeyboardBuilder()
    for uid, pdata in candidates:
        if uid == str(voter_id):
            continue
        builder.button(text=pdata["name"], callback_data=f"votefor:{game_id}:{uid}")
    builder.adjust(1)
    return builder.as_markup()


def yes_no_keyboard(game_id: str, prefix: str) -> InlineKeyboardMarkup:
    """Иә / Жоқ таңдауы үшін жалпы мақсаттағы батырма жиынтығы."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Иә", callback_data=f"{prefix}:{game_id}:yes")
    builder.button(text="❌ Жоқ", callback_data=f"{prefix}:{game_id}:no")
    builder.adjust(2)
    return builder.as_markup()
