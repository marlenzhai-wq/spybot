"""
Боттың барлық хендлерлері: командалар, callback батырмалары және
админнің мәтіндік енгізуін өңдейтін хендлер.

Барлық ойын логикасы боттың жеке чатында (private) жүреді.
"""

import logging
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import game_logic
import keyboards
from config import ADMIN_IDS
from database import storage
from states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    """Қолданушының админ құқығы бар-жоғын тексереді."""
    return user_id in ADMIN_IDS


def _find_admin_playing_game(admin_id: int) -> Optional[str]:
    """Админнің "playing" күйіндегі белсенді ойынын табады (/vote командасы үшін)."""
    for gid, g in storage.get_admin_games(admin_id).items():
        if g["status"] == "playing":
            return gid
    return None


# ---------------------------------------------------------------------------
# /start — ойыншы сілтеме арқылы қосылады немесе жай сәлемдесу хабарламасы
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    """/start немесе /start GAME_xxxxx (deep link арқылы қосылу)."""
    payload = command.args

    if payload and payload.startswith("GAME_"):
        await _handle_join(message, payload)
        return

    await message.answer(
        "Сәлем! Бұл — Шпион ойыны боты. 🕵️\n\n"
        "Егер сізде ойынға қосылу сілтемесі болса, соны басыңыз.\n"
        "Админдер жаңа ойын жасау үшін /newgame командасын қолдана алады."
    )


async def _handle_join(message: Message, game_id: str) -> None:
    """Ойыншыны сілтеме арқылы ойынға қосу логикасы."""
    game = storage.get_game(game_id)
    if not game:
        await message.answer("Бұл ойын табылмады немесе аяқталған.")
        return
    if game["status"] != "waiting":
        await message.answer("Бұл ойын қазірдің өзінде басталып кетті.")
        return

    name = message.from_user.full_name
    added = game_logic.add_player(game_id, message.from_user.id, name)
    if not added:
        await message.answer("Ойынға қосылу мүмкін болмады.")
        return

    await message.answer("Сіз ойынға қосылдыңыз.")

    game = storage.get_game(game_id)
    try:
        await message.bot.send_message(
            game["admin_id"],
            game_logic.get_players_list_text(game),
            reply_markup=keyboards.start_game_keyboard(game_id),
        )
    except Exception as e:
        logger.warning(f"Әкімге хабарлама жіберу мүмкін болмады: {e}")


# ---------------------------------------------------------------------------
# /newgame — жаңа ойын жасау (тек админ)
# ---------------------------------------------------------------------------

@router.message(Command("newgame"))
async def cmd_newgame(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Бұл команда тек админдерге қолжетімді.")
        return

    game_id = game_logic.generate_game_id()
    storage.create_game(game_id, message.from_user.id)

    bot_info = await message.bot.get_me()
    join_link = f"https://t.me/{bot_info.username}?start={game_id}"

    await message.answer(
        "Жаңа ойын жасалды!\n\n"
        f"Ойыншыларға осы сілтемені жіберіңіз:\n{join_link}\n\n"
        + game_logic.get_players_list_text(storage.get_game(game_id)),
        reply_markup=keyboards.start_game_keyboard(game_id),
    )


# ---------------------------------------------------------------------------
# Ойыншылар тізімін жаңарту
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("refresh:"))
async def cb_refresh(callback: CallbackQuery):
    game_id = callback.data.split(":", 1)[1]
    game = storage.get_game(game_id)
    if not game or game["admin_id"] != callback.from_user.id:
        await callback.answer("Қолжетімсіз.", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            game_logic.get_players_list_text(game),
            reply_markup=keyboards.start_game_keyboard(game_id),
        )
    except Exception:
        pass  # мәтін өзгермеген болса Telegram қате қайтарады, елемей кетеміз
    await callback.answer()


# ---------------------------------------------------------------------------
# Ойынды бастау
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("startgame:"))
async def cb_startgame(callback: CallbackQuery):
    game_id = callback.data.split(":", 1)[1]
    game = storage.get_game(game_id)
    if not game or game["admin_id"] != callback.from_user.id:
        await callback.answer("Қолжетімсіз.", show_alert=True)
        return

    if game["status"] != "waiting":
        await callback.answer("Ойын қазірдің өзінде басталған.", show_alert=True)
        return

    if not game_logic.has_enough_players(game):
        await callback.answer("Қатысушылар жеткіліксіз.", show_alert=True)
        return

    game["status"] = "choosing_spy_count"
    storage.update_game(game_id, game)

    await callback.message.answer(
        "Неше шпион болады?",
        reply_markup=keyboards.spy_count_keyboard(game_id, len(game["players"])),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шпион санын таңдау
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("spycount:"))
async def cb_spycount(callback: CallbackQuery, state: FSMContext):
    _, game_id, n = callback.data.split(":")
    game = storage.get_game(game_id)
    if not game or game["admin_id"] != callback.from_user.id:
        await callback.answer("Қолжетімсіз.", show_alert=True)
        return

    if game["status"] != "choosing_spy_count":
        await callback.answer("Бұл әрекет қазір қолжетімсіз.", show_alert=True)
        return

    game["spy_count"] = int(n)
    game["status"] = "entering_word"
    storage.update_game(game_id, game)

    await state.set_state(AdminStates.waiting_for_word)
    await state.update_data(game_id=game_id)

    await callback.message.answer("Раундтың сөзін енгізіңіз.")
    await callback.answer()


# ---------------------------------------------------------------------------
# Сөзді қабылдау (бірінші раунд немесе жаңа раунд)
# ---------------------------------------------------------------------------

@router.message(AdminStates.waiting_for_word)
async def process_word_input(message: Message, state: FSMContext):
    data = await state.get_data()
    game_id = data.get("game_id")
    game = storage.get_game(game_id)

    if not game or game["admin_id"] != message.from_user.id:
        await state.clear()
        return

    word = (message.text or "").strip()
    if not word:
        await message.answer("Сөз бос болмауы керек. Қайта енгізіңіз.")
        return

    await state.clear()

    if not game["roles_assigned"]:
        # Бірінші раунд — рөлдер алғаш рет таратылады
        game_logic.assign_roles_and_word(game, game["spy_count"], word)
        storage.update_game(game_id, game)
        await distribute_roles(message.bot, game, game_id)
    else:
        # Ойын жалғасуда — тек жаңа сөз таратылады
        game_logic.start_new_round(game, new_word=word)
        storage.update_game(game_id, game)
        await distribute_new_word(message.bot, game)
        await message.answer(
            "Жаңа сөз тірі бейбіт ойыншыларға жіберілді.",
            reply_markup=keyboards.vote_button_keyboard(game_id),
        )


async def distribute_roles(bot: Bot, game: dict, game_id: str) -> None:
    """Әр ойыншыға өз рөлін/сөзін жеке чатта жібереді, әкімге шпиондар тізімін жібереді."""
    for uid, pdata in game["players"].items():
        try:
            if pdata["role"] == "spy":
                await bot.send_message(int(uid), "Сіз — ШПИОН.")
            else:
                await bot.send_message(int(uid), f"Сіздің сөзіңіз:\n\n{pdata['word']}")
        except Exception as e:
            logger.warning(f"{uid} қолданушысына хабарлама жіберу мүмкін болмады: {e}")

    spy_names = [game["players"][uid]["name"] for uid in game["spies"]]
    await bot.send_message(
        game["admin_id"],
        "Шпиондар:\n\n" + "\n".join(spy_names),
        reply_markup=keyboards.vote_button_keyboard(game_id),
    )


async def distribute_new_word(bot: Bot, game: dict) -> None:
    """Жаңа сөзді тек тірі бейбіт ойыншыларға жібереді, шпиондарға ештеңе жіберілмейді."""
    for uid, pdata in game["players"].items():
        if pdata["alive"] and pdata["role"] == "civilian":
            try:
                await bot.send_message(int(uid), f"Сіздің сөзіңіз:\n\n{pdata['word']}")
            except Exception as e:
                logger.warning(f"{uid} қолданушысына хабарлама жіберу мүмкін болмады: {e}")


# ---------------------------------------------------------------------------
# Дауыс беруді бастау (/vote немесе батырма)
# ---------------------------------------------------------------------------

@router.message(Command("vote"))
async def cmd_vote(message: Message):
    if not is_admin(message.from_user.id):
        return

    game_id = _find_admin_playing_game(message.from_user.id)
    if not game_id:
        await message.answer("Сізде дауыс беруге дайын белсенді ойын жоқ.")
        return

    await start_voting(message.bot, game_id)
    await message.answer("Дауыс беру басталды.")


@router.callback_query(F.data.startswith("vote_start:"))
async def cb_vote_start(callback: CallbackQuery):
    game_id = callback.data.split(":", 1)[1]
    game = storage.get_game(game_id)
    if not game or game["admin_id"] != callback.from_user.id:
        await callback.answer("Қолжетімсіз.", show_alert=True)
        return

    if game["status"] != "playing":
        await callback.answer("Дауыс беру қазір қолжетімсіз.", show_alert=True)
        return

    await start_voting(callback.bot, game_id)
    await callback.answer("Дауыс беру басталды.")


async def start_voting(bot: Bot, game_id: str) -> None:
    """Барлық тірі ойыншыларға дауыс беру батырмаларын жеке чатта жібереді."""
    game = storage.get_game(game_id)
    game["status"] = "voting"
    game["votes"] = {}
    storage.update_game(game_id, game)

    alive = game_logic.get_alive_players(game)
    for uid, pdata in alive:
        try:
            await bot.send_message(
                int(uid),
                "Кімді шығарамыз?",
                reply_markup=keyboards.voting_targets_keyboard(game_id, alive, int(uid)),
            )
        except Exception as e:
            logger.warning(f"{uid} қолданушысына хабарлама жіберу мүмкін болмады: {e}")


# ---------------------------------------------------------------------------
# Дауыс беру батырмасын басу
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("votefor:"))
async def cb_votefor(callback: CallbackQuery):
    _, game_id, target_id = callback.data.split(":")
    game = storage.get_game(game_id)
    if not game:
        await callback.answer("Ойын табылмады.", show_alert=True)
        return

    voter_id = callback.from_user.id
    voter = game["players"].get(str(voter_id))
    if not voter or not voter["alive"]:
        await callback.answer("Сіз бұл дауыс беруге қатыса алмайсыз.", show_alert=True)
        return

    if game["status"] not in ("voting", "revote"):
        await callback.answer("Дауыс беру қазір белсенді емес.", show_alert=True)
        return

    if game["status"] == "revote" and target_id not in game.get("tie_candidates", []):
        await callback.answer("Бұл ойыншыға дауыс беруге болмайды.", show_alert=True)
        return

    ok = game_logic.register_vote(game, voter_id, int(target_id))
    if not ok:
        await callback.answer("Сіз бұрын дауыс бердіңіз.", show_alert=True)
        return

    storage.update_game(game_id, game)
    await callback.answer("Дауысыңыз қабылданды.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if game_logic.all_alive_have_voted(game):
        await finalize_voting(callback.bot, game_id)


async def finalize_voting(bot: Bot, game_id: str) -> None:
    """Барлық тірі ойыншы дауыс бергеннен кейін нәтижені есептеп, келесі қадамды бастайды."""
    game = storage.get_game(game_id)
    counts, top, _ = game_logic.tally_votes(game)

    report_lines = []
    for voter_id, target_id in game["votes"].items():
        voter_name = game["players"][voter_id]["name"]
        target_name = game["players"][target_id]["name"]
        report_lines.append(f"{voter_name} → {target_name}")

    report_lines.append("")
    for uid, count in counts.items():
        report_lines.append(f"{game['players'][uid]['name']} — {count} дауыс")

    if len(top) > 1:
        await _handle_tie(bot, game, game_id, top, report_lines)
        return

    eliminated_id = top[0]
    eliminated_name = game["players"][eliminated_id]["name"]
    game_logic.eliminate_player(game, eliminated_id)

    report_lines.append("")
    report_lines.append(f"Ең көп дауыс жинаған:\n{eliminated_name}\n\nОйыннан шығарылды.")
    await bot.send_message(game["admin_id"], "\n".join(report_lines))

    result = game_logic.check_win_condition(game)
    if result == "civilians":
        game["status"] = "finished"
        storage.update_game(game_id, game)
        await bot.send_message(game["admin_id"], "Ойын аяқталды! Бейбіт ойыншылар жеңді. 🎉")
        return

    if result == "spies":
        game["status"] = "finished"
        storage.update_game(game_id, game)
        await bot.send_message(game["admin_id"], "Ойын аяқталды! Шпиондар жеңді. 🕵️")
        return

    game["status"] = "round_end_decision"
    storage.update_game(game_id, game)
    await bot.send_message(
        game["admin_id"],
        "Жаңа сөз енгізесіз бе?",
        reply_markup=keyboards.yes_no_keyboard(game_id, "newword"),
    )


async def _handle_tie(bot: Bot, game: dict, game_id: str, top: list, report_lines: list) -> None:
    """Тең дауыс жағдайында қайта дауыс беруді бастайды."""
    top_names = [game["players"][uid]["name"] for uid in top]
    report_lines.append("")
    report_lines.append("Тең дауыс. Қайта дауыс беру басталады:\n" + ", ".join(top_names))
    await bot.send_message(game["admin_id"], "\n".join(report_lines))

    game["status"] = "revote"
    game["tie_candidates"] = top
    game["votes"] = {}
    storage.update_game(game_id, game)

    alive = game_logic.get_alive_players(game)
    candidates = [(uid, game["players"][uid]) for uid in top]
    for uid, _pdata in alive:
        try:
            await bot.send_message(
                int(uid),
                "Қайта дауыс беру. Кімді шығарамыз?",
                reply_markup=keyboards.voting_targets_keyboard(game_id, candidates, int(uid)),
            )
        except Exception as e:
            logger.warning(f"{uid} қолданушысына хабарлама жіберу мүмкін болмады: {e}")


# ---------------------------------------------------------------------------
# Жаңа раунд үшін жаңа сөз енгізу керек пе деген шешім
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("newword:"))
async def cb_newword(callback: CallbackQuery, state: FSMContext):
    _, game_id, choice = callback.data.split(":")
    game = storage.get_game(game_id)
    if not game or game["admin_id"] != callback.from_user.id:
        await callback.answer("Қолжетімсіз.", show_alert=True)
        return

    if game["status"] != "round_end_decision":
        await callback.answer("Бұл әрекет қазір қолжетімсіз.", show_alert=True)
        return

    if choice == "yes":
        game["status"] = "entering_word"
        storage.update_game(game_id, game)
        await state.set_state(AdminStates.waiting_for_word)
        await state.update_data(game_id=game_id)
        await callback.message.answer("Раундтың сөзін енгізіңіз.")
    else:
        game["status"] = "playing"
        storage.update_game(game_id, game)
        await callback.message.answer(
            "Ойын жалғасады. Дайын болғанда дауыс беруді қайта бастаңыз.",
            reply_markup=keyboards.vote_button_keyboard(game_id),
        )

    await callback.answer()
