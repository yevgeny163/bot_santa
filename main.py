import asyncio  
import random  
import string  
import os
from typing import Dict, List, Optional  
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, types  

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN")  
# If token is still placeholder, show helpful message
if TOKEN == "YOUR_TOKEN":
    raise ValueError(
        "⚠️ TOKEN не установлен!\n"
        "Создайте файл .env в корне проекта и добавьте:\n"
        "BOT_TOKEN=your_actual_token_here"
    )  


# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------  

def normalize_name(s: str) -> str:  
    """  
    Нормализация имени:  
    - обрезаем пробелы  
    - приводим к нижнему регистру  
    - ё -> е  
    - сжимаем несколько пробелов в один  
    """  
    s = s.strip().lower()  
    s = s.replace("ё", "е")  
    s = " ".join(s.split())  
    return s  


def make_derangement(items: List[str]) -> List[str]:  
    """  
    Делает случайную перестановку без неподвижных точек:  
    никто не получает сам себя.  
    items: список имён (в фиксированном порядке).  
    """  
    if len(items) < 2:  
        raise ValueError("Нужно минимум 2 участника для Тайного Санты")  

    base = items[:]  

    while True:  
        shuffled = base[:]  
        random.shuffle(shuffled)  
        if all(a != b for a, b in zip(base, shuffled)):  
            return shuffled  


def generate_game_id(length: int = 4) -> str:  
    """  
    Генерирует короткий код игры, например: A7F9.  
    """  
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без похожих символов типа 0/O/1/I  
    while True:  
        code = "".join(random.choice(alphabet) for _ in range(length))  
        if code not in games:  
            return code  


# ---------- СТРУКТУРА ИГРЫ ----------  

class Game:  
    def __init__(self, organizer_id: int, names_pretty: List[str]):  
        """  
        names_pretty — список имён, как прислал организатор (красивый вид).  
        """  
        self.organizer_id: int = organizer_id  

        # оставляем только уникальные имена по нормализованной форме  
        name_index: Dict[str, str] = {}  
        unique_pretty: List[str] = []  
        for pretty in names_pretty:  
            pretty = pretty.strip()  
            if not pretty:  
                continue  
            norm = normalize_name(pretty)  
            if norm in name_index:  
                # дубликаты пропускаем — лучше различать вручную  
                continue  
            name_index[norm] = pretty  
            unique_pretty.append(pretty)  

        if len(unique_pretty) < 2:  
            raise ValueError("После удаления дубликатов осталось меньше 2 участников.")  

        self.names: List[str] = unique_pretty                  # красивый список  
        self.name_index: Dict[str, str] = name_index           # norm -> pretty  
        self.assignment_by_name: Dict[str, str] = {}           # pretty -> pretty_получатель  
        self.user_names: Dict[int, str] = {}                   # user_id -> pretty_name  

        # генерируем распределение Санты  
        receivers = make_derangement(self.names)  
        self.assignment_by_name = {  
            giver: receiver for giver, receiver in zip(self.names, receivers)  
        }  


# ---------- ГЛОБАЛЬНОЕ СОСТОЯНИЕ БОТА ----------  

bot = Bot(token=TOKEN)  
dp = Dispatcher()  

# все активные игры: game_id -> Game  
games: Dict[str, Game] = {}  

# организатор -> код игры, от которого сейчас ждём список участников  
pending_game_codes: Dict[int, str] = {}  

# организатор -> код активной игры (после того как список принят)  
organizer_games: Dict[int, str] = {}  

# пользователь -> код игры, в которой он участвует  
user_games: Dict[int, str] = {}  


# ------------------ ОБРАБОТЧИКИ КОМАНД ------------------  


@dp.message(F.text == "/help")  
async def cmd_help(message: types.Message):  
    text = (  
        "🎄 *Тайный Санта — бот*\n\n"  
        "*Для организатора:*\n"  
        "1. Напиши /newgame — я создам *код игры*.\n"  
        "2. В ответ пришли список участников: по одному `Имя Фамилия` в каждой строке.\n"  
        "3. Отправь участникам код игры и ссылку на бота.\n\n"  
        "*Для участника:*\n"  
        "1. Напиши /start.\n"  
        "2. Введи *код игры* от организатора (например: `A7F9`).\n"  
        "3. Потом введи свои имя и фамилию.\n"  
        "4. Нажми кнопку «🎁 Получить имя».\n\n"  
        "*Бот:*\n"  
        "- никому не даёт самого себя\n"  
        "- один и тот же человек выдаётся только одному участнику\n"  
        "- ты можешь нажимать кнопку сколько угодно — твой человек не поменяется."  
    )  
    await message.answer(text, parse_mode="Markdown")  


@dp.message(F.text == "/start")  
async def cmd_start(message: types.Message):  
    await message.answer(  
        "Привет! 🎄\n\n"  
        "Если ты *организатор* — напиши \n/newgame и создай список участников.\n\n"  
        "Если ты *участник* — отправь мне *код игры*, который тебе дал организатор.\n"  
        "Например: `A7F9`.",  
        parse_mode="Markdown",  
    )  


@dp.message(F.text == "/newgame")  
async def cmd_newgame(message: types.Message):  
    """  
    Создание новой игры. Вызывается организатором.  
    После этого бот ждёт список участников в следующем сообщении.  
    """  
    organizer_id = message.from_user.id  

    game_id = generate_game_id()  
    pending_game_codes[organizer_id] = game_id  

    await message.answer(  
        "Окей! 🎄\n"  
        f"Код вашей игры: *{game_id}*.\n\n"  
        "1️⃣ Сначала пришлите список участников *одним сообщением*.\n"  
        "Каждый участник — в отдельной строке, формат: `Имя Фамилия`.\n"  
        "Минимум 2 человека.\n\n"  
        "2️⃣ Потом отправьте участникам *код игры* и ссылку на бота.\n",  
        parse_mode="Markdown",  
    )  


@dp.message(F.text == "/reset")  
async def cmd_reset(message: types.Message):  
    """  
    Полный сброс игры организатора (последней активной).  
    """  
    organizer_id = message.from_user.id  

    if organizer_id not in organizer_games:  
        await message.answer("У вас сейчас нет активной игры, сбрасывать нечего 🙂")  
        return  

    game_id = organizer_games[organizer_id]  
    game = games.get(game_id)  
    if game:  
        # убираем всех участников этой игры  
        for uid in list(game.user_names.keys()):  
            user_games.pop(uid, None)  

    games.pop(game_id, None)  
    pending_game_codes.pop(organizer_id, None)  
    organizer_games.pop(organizer_id, None)  

    await message.answer(  
        f"Игра с кодом *{game_id}* полностью сброшена. "  
        "Можно запустить новую через /newgame.",  
        parse_mode="Markdown",  
    )  


@dp.message(F.text == "🎁 Получить имя")  
async def handle_get_recipient(message: types.Message):  
    """  
    Участник просит своего получателя.  
    """  
    user_id = message.from_user.id  

    if user_id not in user_games:  
        await message.answer(  
            "Сначала присоединись к игре:\n"  
            "1) /start\n"  
            "2) введи код игры от организатора\n"  
            "3) введи свои имя и фамилию 🙂"  
        )  
        return  

    game_id = user_games[user_id]  
    game = games.get(game_id)  

    if game is None:  
        await message.answer(  
            "Похоже, игра уже была сброшена организатором 😔\n"  
            "Спросите у него, не создавал ли он новую игру."  
        )  
        return  

    if user_id not in game.user_names:  
        await message.answer(  
            "Сначала напиши своё *имя и фамилию* как в списках у организатора, чтобы я понял, кто ты 🙂",  
            parse_mode="Markdown",  
        )  
        return  

    my_name = game.user_names[user_id]  
    recipient = game.assignment_by_name.get(my_name)  

    if not recipient:  
        await message.answer(  
            "Произошла внутренняя ошибка при поиске получателя 😔\n"  
            "Попроси организатора сбросить игру командой /reset и создать её заново."  
        )  
        return  

    await message.answer(  
        f"Твой человек: **{recipient}** 🎁\nНикому не рассказывай 😉",  
        parse_mode="Markdown",  
    )  


# ------------------ ОБРАБОТЧИК ВСЕГО ОСТАЛЬНОГО ТЕКСТА ------------------  


@dp.message()  
async def handle_text(message: types.Message):  
    """  
    Здесь три ситуации:  
    1) Ждём список участников от организатора после /newgame  
    2) Пользователь вводит код игры, чтобы присоединиться  
    3) Пользователь (уже в игре) вводит своё имя и фамилию  
    """  
    text = (message.text or "").strip()  
    user_id = message.from_user.id  

    # Игнорируем неизвестные команды  
    if text.startswith("/"):  
        await message.answer("Неизвестная команда. Попробуй /help 🙂")  
        return  

    # --- 1) Организатор присылает список участников ---  
    if user_id in pending_game_codes:  
        game_id = pending_game_codes[user_id]  

        lines = [line.strip() for line in text.splitlines() if line.strip()]  
        if len(lines) < 2:  
            await message.answer(  
                "В списке должно быть минимум *два* участника.\n"  
                "Пришлите, пожалуйста, список ещё раз.",  
                parse_mode="Markdown",  
            )  
            return  

        try:  
            game = Game(organizer_id=user_id, names_pretty=lines)  
        except ValueError as e:  
            await message.answer(f"Ошибка в списке участников: {e}")  
            return  

        games[game_id] = game  
        organizer_games[user_id] = game_id  
        pending_game_codes.pop(user_id, None)  

        await message.answer(  
            f"Новая игра создана! 🎄\n"  
            f"Код игры: *{game_id}*\n"  
            f"Участников: *{len(game.names)}*.\n\n"  
            "Теперь отправь участникам:\n"  
            f"— ссылку на бота\n"  
            f"— код игры: `{game_id}`\n\n"  
            "Участники:\n"  
            "1) заходят к боту\n"  
            "2) пишут /start\n"  
            "3) вводят код игры\n"  
            "4) вводят свои имя и фамилию\n"  
            "5) нажимают «🎁 Получить имя»",  
            parse_mode="Markdown",  
        )  
        return  

    # --- 2) Пользователь вводит код игры, чтобы присоединиться ---  
    if user_id not in user_games:  
        game_id = text.upper()  
        game = games.get(game_id)  

        if game is None:  
            await message.answer(  
                "Я не нашёл игру с таким кодом 😔\n"  
                "Проверь, правильно ли ты ввёл код (например: `A7F9`).",  
                parse_mode="Markdown",  
            )  
            return  

        user_games[user_id] = game_id  
        await message.answer(  
            f"Игра с кодом *{game_id}* найдена! 🎄\n"  
            "Теперь напиши свои *имя и фамилию* так, как они есть в списке у организатора.\n",  
            parse_mode="Markdown",  
        )  
        return  

    # --- 3) Пользователь уже в игре — вводит своё имя и фамилию ---  
    game_id = user_games[user_id]  
    game = games.get(game_id)  

    if game is None:  
        await message.answer(  
            "Похоже, игра уже была сброшена организатором 😔\n"  
            "Спросите у него, не создавал ли он новую игру."  
        )  
        return  

    norm = normalize_name(text)  
    if norm not in game.name_index:  
        await message.answer(  
            "Я не нашёл тебя в списке участников 😔\n\n"  
            "Напиши *имя и фамилию* так, как они есть в списке у организатора,\n"  
            "в одну строку.\n\n"  
            "Например:\n"  
            "`Евгения Дмитриева`\n"  
            "`Юлия Павликова`",  
            parse_mode="Markdown",  
        )  
        return  

    pretty_name = game.name_index[norm]  
    game.user_names[user_id] = pretty_name  

    kb = types.ReplyKeyboardMarkup(  
        keyboard=[[types.KeyboardButton(text="🎁 Получить имя")]],  
        resize_keyboard=True,  
    )  

    await message.answer(  
        f"Отлично, {pretty_name}! 🎄\n"  
        f"Твоё имя записано.\nТеперь нажми кнопку \n«🎁 Получить имя», чтобы узнать, кому ты даришь подарок.",  
        reply_markup=kb,  
    )  


# ---------------------- ЗАПУСК БОТА ----------------------  


async def main():  
    await dp.start_polling(bot)  


asyncio.run(main())  