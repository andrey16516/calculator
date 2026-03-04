import os
import math
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

# -------------------- TOKEN --------------------

def load_token() -> str:
    t = os.getenv("BOT_TOKEN")
    if t and t.strip():
        return t.strip()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "token.txt")
    if not os.path.exists(path):
        raise RuntimeError("Не найден токен. Создайте token.txt рядом с bot.py и вставьте токен одной строкой.")
    with open(path, "r", encoding="utf-8") as f:
        token = f.read().strip()
    if not token:
        raise RuntimeError("Файл token.txt пустой.")
    return token


bot = Bot(token=load_token())
dp = Dispatcher(bot, storage=MemoryStorage())


# -------------------- METALS / ASSAYS --------------------

RHO_REF = 13.6  # reference density for our fitted coefficients (gold 585)

GOLD_ASSAYS = {
    "999": 19.3,
    "958": 18.52,
    "916": 17.59,
    "900": 17.5,
    "850": 16.0,
    "750": 15.6,
    "585": 13.6,
    "583": 13.2,
    "500": 12.5,
    "375": 11.5,
}

SILVER_ASSAYS = {
    "999": 10.5,
    "960": 10.43,
    "925": 10.36,
    "875": 10.28,
    "830": 10.19,
    "800": 10.13,
}

DEFAULT_CHAIN_METAL = ("gold", "585")
DEFAULT_RING_METAL = ("gold", "585")


def metal_title(group: str, assay: str) -> str:
    return f"{'Золото' if group == 'gold' else 'Серебро'} {assay}"

def metal_rho(group: str, assay: str) -> float:
    return (GOLD_ASSAYS if group == "gold" else SILVER_ASSAYS)[assay]


# -------------------- WEAVES --------------------

@dataclass(frozen=True)
class WeaveCfg:
    ui_name: str
    model: str                    # "emp_k" | "emp_c"
    k_ref: float | None
    c_ref: float | None
    rigel_factor: float

    d_round_mode: str             # "round" | "floor"
    d_round_step: float
    D_round_mode: str
    D_round_step: float

    w_before_factor: float | None
    w_after_factor: float | None
    w_round_step: float | None


WEAVES = {
    "Бисмарк": WeaveCfg("Бисмарк", "emp_k", k_ref=2.4, c_ref=None, rigel_factor=2.7,
                        d_round_mode="round", d_round_step=0.01, D_round_mode="round", D_round_step=0.1,
                        w_before_factor=None, w_after_factor=None, w_round_step=None),

    "Московский бисмарк": WeaveCfg("Московский бисмарк", "emp_k", k_ref=2.7, c_ref=None, rigel_factor=2.8,
                                   d_round_mode="floor", d_round_step=0.01, D_round_mode="floor", D_round_step=0.1,
                                   w_before_factor=None, w_after_factor=None, w_round_step=None),

    "Московский бит": WeaveCfg("Московский бит", "emp_k", k_ref=1.28, c_ref=None, rigel_factor=2.27,
                               d_round_mode="round", d_round_step=0.01, D_round_mode="round", D_round_step=0.1,
                               w_before_factor=None, w_after_factor=None, w_round_step=None),

    "Рамзес": WeaveCfg("Рамзес", "emp_c", k_ref=None, c_ref=0.50625, rigel_factor=2.8,
                       d_round_mode="round", d_round_step=0.01, D_round_mode="round", D_round_step=0.1,
                       w_before_factor=None, w_after_factor=None, w_round_step=None),

    "Американка": WeaveCfg("Американка (Итальянка)", "emp_c", k_ref=None, c_ref=0.807, rigel_factor=5.0,
                           d_round_mode="round", d_round_step=0.01, D_round_mode="round", D_round_step=0.1,
                           w_before_factor=None, w_after_factor=None, w_round_step=None),

    "Лисий хвост (византия)": WeaveCfg("Лисий хвост (византия)", "emp_c", k_ref=None, c_ref=0.919, rigel_factor=3.30,
                                       d_round_mode="round", d_round_step=0.01, D_round_mode="round", D_round_step=0.01,
                                       w_before_factor=1.667, w_after_factor=1.531, w_round_step=0.01),

    "Якорное": WeaveCfg("Якорное", "emp_c", k_ref=None, c_ref=3.079, rigel_factor=2.30,
                        d_round_mode="round", d_round_step=0.01, D_round_mode="round", D_round_step=0.1,
                        w_before_factor=None, w_after_factor=None, w_round_step=None),

    "Панцирное": WeaveCfg("Панцирное", "emp_c", k_ref=None, c_ref=2.45, rigel_factor=2.40,
                          d_round_mode="round", d_round_step=0.1, D_round_mode="round", D_round_step=0.1,
                          w_before_factor=None, w_after_factor=None, w_round_step=None),

    "Шопард": WeaveCfg("Шопард", "emp_c", k_ref=None, c_ref=4.20, rigel_factor=1.80,
                       d_round_mode="round", d_round_step=0.01, D_round_mode="round", D_round_step=0.1,
                       w_before_factor=None, w_after_factor=None, w_round_step=None),
}

PHOTO_FILES = {
    "Бисмарк": "bismarck.jpg",
    "Московский бисмарк": "moscow_bismarck.jpg",
    "Московский бит": "moscow_bit.jpg",
    "Рамзес": "ramzes.jpg",
    "Американка": "american.jpg",
    "Лисий хвост (византия)": "foxtail.jpg",
    "Якорное": "anchor.jpg",
    "Панцирное": "armor.jpg",
    "Шопард": "chopard.jpg",
}

# -------------------- SOLDER CONFIG (GOLD ONLY) --------------------

CLASSIC_850_PER_1G = {"Ag": 0.13, "Cu": 0.13, "Zn": 0.06, "Cd": 0.10}
REFRACTORY_850_PER_1G = {"Ag": 0.10, "Cu": 0.22, "Zn": 0.02}

# -------------------- RINGS CONFIG --------------------

RING_SEMIROUND_K = 0.766  # fitted to your data


# -------------------- UTIL --------------------

def parse_float(text: str) -> float:
    return float(text.replace(",", ".").strip())

def floor_to_step(x: float, step: float) -> float:
    return math.floor(x / step) * step

def round_to_step(x: float, step: float) -> float:
    return round(x / step) * step

def apply_round(x: float, mode: str, step: float) -> float:
    if mode == "floor":
        return floor_to_step(x, step)
    return round_to_step(x, step)

def round2(x: float) -> float:
    return round(x + 1e-12, 2)

def fmt_g(x: float) -> str:
    return f"{round2(x):.2f}"

def file_near_script(filename: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)

async def send_weave_photo_if_exists(message: types.Message, weave_key: str):
    fname = PHOTO_FILES.get(weave_key)
    if not fname:
        return
    path = file_near_script(fname)
    if os.path.exists(path):
        await message.answer_photo(InputFile(path), caption=f"Плетение: {WEAVES[weave_key].ui_name}")


# -------------------- MATH (CHAINS) --------------------

def d_emp_k(M: float, L: float, k: float) -> float:
    return math.sqrt((3.0 * M) / (k * L))

def d_emp_c(M: float, L: float, c: float) -> float:
    return math.sqrt(c * (M / L))

def calc_chain(rho: float, weave_key: str, L: float, M: float) -> dict:
    if M <= 0 or L <= 0:
        raise ValueError

    w = WEAVES[weave_key]

    if w.model == "emp_k":
        k = w.k_ref * (rho / RHO_REF)
        d = d_emp_k(M, L, k)
    else:
        c = w.c_ref * (RHO_REF / rho)
        d = d_emp_c(M, L, c)

    D = d * w.rigel_factor

    d_out = apply_round(d, w.d_round_mode, w.d_round_step)
    D_out = apply_round(D, w.D_round_mode, w.D_round_step)

    out = {"d": d_out, "D": D_out}

    if w.w_before_factor and w.w_after_factor and w.w_round_step:
        out["w_before"] = apply_round(D_out * w.w_before_factor, "round", w.w_round_step)
        out["w_after"] = apply_round(D_out * w.w_after_factor, "round", w.w_round_step)

    return out


# -------------------- MATH (SOLDER) --------------------

def scale_recipe(recipe: dict, grams: float) -> dict:
    return {k: recipe[k] * grams for k in recipe}


# -------------------- MATH (RINGS) --------------------

def ring_shank_length_mm(d_in_mm: float, t_mm: float) -> float:
    return math.pi * (d_in_mm + t_mm)

def ring_weight_rect_g(rho: float, L_mm: float, w_mm: float, t_mm: float) -> float:
    return rho * ((w_mm * t_mm * L_mm) / 1000.0)

def ring_weight_semiround_g(rho: float, L_mm: float, w_mm: float, t_mm: float) -> float:
    return rho * ((RING_SEMIROUND_K * w_mm * t_mm * L_mm) / 1000.0)


# -------------------- MATH (TUBE) --------------------

def tube_blank_width(mode: str, thickness: float, diameter: float) -> float:
    if mode == "inner":
        return math.pi * (diameter + thickness)
    if mode == "outer":
        return math.pi * (diameter - thickness)
    return math.pi * diameter


# -------------------- KEYBOARDS --------------------

def kb_main():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🧮 Расчет цепи"))
    kb.add(KeyboardButton("🧪 Припой"))
    kb.add(KeyboardButton("💍 Расчет обручальных колец"))
    kb.add(KeyboardButton("Расчет трубки"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_chain_metals():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("Золото 585"), KeyboardButton("Серебро 925"))
    kb.row(KeyboardButton("Золото другая проба"), KeyboardButton("Серебро другая проба"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_gold_assays():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    assays = list(GOLD_ASSAYS.keys())
    for i in range(0, len(assays), 2):
        kb.row(*[KeyboardButton(a) for a in assays[i:i+2]])
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_silver_assays():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    assays = list(SILVER_ASSAYS.keys())
    for i in range(0, len(assays), 2):
        kb.row(*[KeyboardButton(a) for a in assays[i:i+2]])
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_weaves():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("Бисмарк"), KeyboardButton("Московский бисмарк"))
    kb.row(KeyboardButton("Московский бит"), KeyboardButton("Рамзес"))
    kb.row(KeyboardButton("Американка"), KeyboardButton("Лисий хвост (византия)"))
    kb.row(KeyboardButton("Якорное"), KeyboardButton("Панцирное"))
    kb.row(KeyboardButton("Шопард"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_after_chain():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔁 Повторить такую же цепь"))
    kb.add(KeyboardButton("🧮 Новый расчет"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_solder_gold_types():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Классический"))
    kb.add(KeyboardButton("Тугоплавкий"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_solder_assay_850():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("850 проба"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_after_solder():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🧪 Еще раз припой"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_ring_metals():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("Золото 585"), KeyboardButton("Серебро 925"))
    kb.row(KeyboardButton("Золото другая проба"), KeyboardButton("Серебро другая проба"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_ring_sections():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("Полукруглое"), KeyboardButton("Прямоугольное"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_after_ring():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("💍 Еще одно кольцо"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_tube_modes():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("Внешний диаметр"), KeyboardButton("Средний диаметр"), KeyboardButton("Внутренний диаметр"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

def kb_after_tube():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Еще расчет трубки"))
    kb.add(KeyboardButton("🏠 В меню"))
    kb.add(KeyboardButton("❌ Отмена"))
    return kb


# -------------------- STATES --------------------

class ChainStates(StatesGroup):
    choosing_metal = State()
    choosing_gold_assay = State()
    choosing_silver_assay = State()
    weave = State()
    length = State()
    mass = State()
    lock_len = State()
    lock_mass = State()
    after = State()

class SolderStates(StatesGroup):
    choosing_type = State()
    choosing_assay = State()
    waiting_grams = State()

class RingStates(StatesGroup):
    choosing_metal = State()
    choosing_gold_assay = State()
    choosing_silver_assay = State()
    section = State()
    d_in = State()
    width = State()
    thickness = State()
    price = State()
    after = State()

class TubeStates(StatesGroup):
    mode = State()
    diameter = State()
    thickness = State()


# -------------------- COMMON --------------------

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Ювелирный калькулятор", reply_markup=kb_main())

@dp.message_handler(lambda m: m.text == "❌ Отмена", state="*")
async def cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Отменено.", reply_markup=kb_main())

@dp.message_handler(lambda m: m.text == "🏠 В меню", state="*")
async def to_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Меню:", reply_markup=kb_main())


# -------------------- CHAINS FLOW --------------------

@dp.message_handler(lambda m: m.text == "🧮 Расчет цепи")
async def chains_entry(message: types.Message, state: FSMContext):
    await state.finish()
    await state.update_data(chain_group=DEFAULT_CHAIN_METAL[0], chain_assay=DEFAULT_CHAIN_METAL[1])
    await message.answer("Выберите металл/пробу:", reply_markup=kb_chain_metals())
    await ChainStates.choosing_metal.set()

@dp.message_handler(lambda m: m.text == "Золото 585", state=ChainStates.choosing_metal)
async def chains_gold_585(message: types.Message, state: FSMContext):
    await state.update_data(chain_group="gold", chain_assay="585")
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await ChainStates.weave.set()

@dp.message_handler(lambda m: m.text == "Серебро 925", state=ChainStates.choosing_metal)
async def chains_silver_925(message: types.Message, state: FSMContext):
    await state.update_data(chain_group="silver", chain_assay="925")
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await ChainStates.weave.set()

@dp.message_handler(lambda m: m.text == "Золото другая проба", state=ChainStates.choosing_metal)
async def chains_gold_other(message: types.Message, state: FSMContext):
    await message.answer("Выберите пробу золота:", reply_markup=kb_gold_assays())
    await ChainStates.choosing_gold_assay.set()

@dp.message_handler(lambda m: m.text in GOLD_ASSAYS.keys(), state=ChainStates.choosing_gold_assay)
async def chains_gold_assay_selected(message: types.Message, state: FSMContext):
    await state.update_data(chain_group="gold", chain_assay=message.text)
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await ChainStates.weave.set()

@dp.message_handler(lambda m: m.text == "Серебро другая проба", state=ChainStates.choosing_metal)
async def chains_silver_other(message: types.Message, state: FSMContext):
    await message.answer("Выберите пробу серебра:", reply_markup=kb_silver_assays())
    await ChainStates.choosing_silver_assay.set()

@dp.message_handler(lambda m: m.text in SILVER_ASSAYS.keys(), state=ChainStates.choosing_silver_assay)
async def chains_silver_assay_selected(message: types.Message, state: FSMContext):
    await state.update_data(chain_group="silver", chain_assay=message.text)
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await ChainStates.weave.set()

@dp.message_handler(lambda m: m.text in WEAVES.keys(), state=ChainStates.weave)
async def chains_choose_weave(message: types.Message, state: FSMContext):
    weave_key = message.text
    await state.update_data(weave=weave_key)
    await send_weave_photo_if_exists(message, weave_key)
    await message.answer("Введите длину изделия (см):")
    await ChainStates.length.set()

@dp.message_handler(lambda m: m.text == "🧮 Новый расчет", state="*")
async def chains_new_calc(message: types.Message, state: FSMContext):
    await chains_entry(message, state)

@dp.message_handler(lambda m: m.text == "🔁 Повторить такую же цепь", state=ChainStates.after)
async def chains_repeat(message: types.Message, state: FSMContext):
    data = await state.get_data()
    weave_key = data.get("weave")
    if not weave_key:
        await state.finish()
        return await message.answer("Сначала сделайте расчет.", reply_markup=kb_main())
    await message.answer(f"Повтор: {WEAVES[weave_key].ui_name}\nВведите длину изделия (см):")
    await ChainStates.length.set()

@dp.message_handler(state=ChainStates.length)
async def chains_length(message: types.Message, state: FSMContext):
    try:
        L_total = parse_float(message.text)
        if L_total <= 0:
            raise ValueError
    except Exception:
        return await message.reply("Длина должна быть числом > 0.")
    await state.update_data(L_total=L_total)
    await message.answer("Введите массу изделия (г):")
    await ChainStates.mass.set()

@dp.message_handler(state=ChainStates.mass)
async def chains_mass(message: types.Message, state: FSMContext):
    try:
        M_total = parse_float(message.text)
        if M_total <= 0:
            raise ValueError
    except Exception:
        return await message.reply("Масса должна быть числом > 0.")
    await state.update_data(M_total=M_total)
    await message.answer("Длина замка + концевиков (см). Если нет — 0:")
    await ChainStates.lock_len.set()

@dp.message_handler(state=ChainStates.lock_len)
async def chains_lock_len(message: types.Message, state: FSMContext):
    try:
        L_lock = parse_float(message.text)
        if L_lock < 0:
            raise ValueError
    except Exception:
        return await message.reply("Введите число >= 0.")

    await state.update_data(L_lock=L_lock)

    if abs(L_lock) < 1e-12:
        await state.update_data(M_lock=0.0)
        return await chains_finish_calc(message, state)

    await message.answer("Масса замка + концевиков (г):")
    await ChainStates.lock_mass.set()

@dp.message_handler(state=ChainStates.lock_mass)
async def chains_lock_mass(message: types.Message, state: FSMContext):
    try:
        M_lock = parse_float(message.text)
        if M_lock < 0:
            raise ValueError
    except Exception:
        return await message.reply("Введите число >= 0.")
    await state.update_data(M_lock=M_lock)
    await chains_finish_calc(message, state)

async def chains_finish_calc(message: types.Message, state: FSMContext):
    data = await state.get_data()

    group = data["chain_group"]
    assay = data["chain_assay"]
    rho = metal_rho(group, assay)
    metal_str = f"{metal_title(group, assay)} (ρ={rho})"

    weave_key = data["weave"]

    L_total = float(data["L_total"])
    M_total = float(data["M_total"])
    L_lock = float(data.get("L_lock", 0.0))
    M_lock = float(data.get("M_lock", 0.0))

    if abs(L_lock) < 1e-12:
        L_weave, M_weave = L_total, M_total
    else:
        L_weave = L_total - L_lock
        M_weave = M_total - M_lock
        if L_weave <= 0:
            await state.finish()
            return await message.answer("Ошибка: длина замка больше/равна длине изделия.", reply_markup=kb_main())
        if M_weave <= 0:
            await state.finish()
            return await message.answer("Ошибка: масса замка больше/равна массе изделия.", reply_markup=kb_main())

    res = calc_chain(rho, weave_key, L_weave, M_weave)

    if abs(L_lock) < 1e-12:
        text = (
            f"📌 Результат цепи\n\n"
            f"Металл: {metal_str}\n"
            f"Плетение: {WEAVES[weave_key].ui_name}\n\n"
            f"Длина: {L_total:.2f} см\n"
            f"Масса: {M_total:.2f} г\n\n"
            f"Диаметр проволоки: {res['d']:.2f} мм\n"
            f"Диаметр ригеля: {res['D']:.2f} мм\n"
        )
    else:
        text = (
            f"📌 Результат цепи\n\n"
            f"Металл: {metal_str}\n"
            f"Плетение: {WEAVES[weave_key].ui_name}\n\n"
            f"Итог изделия:\n"
            f"  Длина: {L_total:.2f} см\n"
            f"  Масса: {M_total:.2f} г\n\n"
            f"Замок+концевики:\n"
            f"  Длина: {L_lock:.2f} см\n"
            f"  Масса: {M_lock:.2f} г\n\n"
            f"Плетение (для расчета):\n"
            f"  Длина: {L_weave:.2f} см\n"
            f"  Масса: {M_weave:.2f} г\n\n"
            f"Диаметр проволоки: {res['d']:.2f} мм\n"
            f"Диаметр ригеля: {res['D']:.2f} мм\n"
        )

    if "w_before" in res and "w_after" in res:
        text += (
            f"\nШирина до припиливания: {res['w_before']:.2f} мм\n"
            f"Ширина после припиливания: {res['w_after']:.2f} мм\n"
        )

    await message.answer(text, reply_markup=kb_after_chain())
    await ChainStates.after.set()


# -------------------- SOLDER FLOW --------------------

@dp.message_handler(lambda m: m.text == "🧪 Припой")
async def solder_entry(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Припой (золото). Выберите тип:", reply_markup=kb_solder_gold_types())
    await SolderStates.choosing_type.set()

@dp.message_handler(lambda m: m.text in ["Классический", "Тугоплавкий"], state=SolderStates.choosing_type)
async def solder_choose_type(message: types.Message, state: FSMContext):
    await state.update_data(solder_type=message.text)
    await message.answer("Выберите пробу исходного металла:", reply_markup=kb_solder_assay_850())
    await SolderStates.choosing_assay.set()

@dp.message_handler(lambda m: m.text == "850 проба", state=SolderStates.choosing_assay)
async def solder_choose_assay(message: types.Message, state: FSMContext):
    await state.update_data(assay=850)
    await message.answer("Сколько грамм пересчитать? (например 1 или 0.5)")
    await SolderStates.waiting_grams.set()

@dp.message_handler(state=SolderStates.waiting_grams)
async def solder_grams(message: types.Message, state: FSMContext):
    grams = parse_float(message.text)
    stype = (await state.get_data()).get("solder_type")
    recipe_per_1g = REFRACTORY_850_PER_1G if stype == "Тугоплавкий" else CLASSIC_850_PER_1G
    recipe = scale_recipe(recipe_per_1g, grams)

    lines = [
        f"🧪 Припой (золото) — {stype.lower()}",
        "Проба исходного металла: 850",
        f"Количество: {round2(grams):.2f} г",
        "",
        f"Ag (серебро): {fmt_g(recipe.get('Ag', 0.0))} г",
        f"Cu (медь): {fmt_g(recipe.get('Cu', 0.0))} г",
        f"Zn (цинк): {fmt_g(recipe.get('Zn', 0.0))} г",
    ]
    if "Cd" in recipe_per_1g:
        lines.append(f"Cd (кадмий): {fmt_g(recipe.get('Cd', 0.0))} г")

    await state.finish()
    await message.answer("\n".join(lines), reply_markup=kb_after_solder())

@dp.message_handler(lambda m: m.text == "🧪 Еще раз припой", state="*")
async def solder_again(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Припой (золото). Выберите тип:", reply_markup=kb_solder_gold_types())
    await SolderStates.choosing_type.set()


# -------------------- RINGS FLOW --------------------

@dp.message_handler(lambda m: m.text == "💍 Расчет обручальных колец")
async def ring_entry(message: types.Message, state: FSMContext):
    await state.finish()
    await state.update_data(ring_group=DEFAULT_RING_METAL[0], ring_assay=DEFAULT_RING_METAL[1])
    await message.answer("Выберите металл/пробу:", reply_markup=kb_ring_metals())
    await RingStates.choosing_metal.set()

@dp.message_handler(lambda m: m.text == "Золото 585", state=RingStates.choosing_metal)
async def ring_gold_585(message: types.Message, state: FSMContext):
    await state.update_data(ring_group="gold", ring_assay="585")
    await message.answer("Выберите сечение:", reply_markup=kb_ring_sections())
    await RingStates.section.set()

@dp.message_handler(lambda m: m.text == "Серебро 925", state=RingStates.choosing_metal)
async def ring_silver_925(message: types.Message, state: FSMContext):
    await state.update_data(ring_group="silver", ring_assay="925")
    await message.answer("Выберите сечение:", reply_markup=kb_ring_sections())
    await RingStates.section.set()

@dp.message_handler(lambda m: m.text == "Золото другая проба", state=RingStates.choosing_metal)
async def ring_gold_other(message: types.Message, state: FSMContext):
    await message.answer("Выберите пробу золота:", reply_markup=kb_gold_assays())
    await RingStates.choosing_gold_assay.set()

@dp.message_handler(lambda m: m.text in GOLD_ASSAYS.keys(), state=RingStates.choosing_gold_assay)
async def ring_gold_assay_selected(message: types.Message, state: FSMContext):
    await state.update_data(ring_group="gold", ring_assay=message.text)
    await message.answer("Выберите сечение:", reply_markup=kb_ring_sections())
    await RingStates.section.set()

@dp.message_handler(lambda m: m.text == "Серебро другая проба", state=RingStates.choosing_metal)
async def ring_silver_other(message: types.Message, state: FSMContext):
    await message.answer("Выберите пробу серебра:", reply_markup=kb_silver_assays())
    await RingStates.choosing_silver_assay.set()

@dp.message_handler(lambda m: m.text in SILVER_ASSAYS.keys(), state=RingStates.choosing_silver_assay)
async def ring_silver_assay_selected(message: types.Message, state: FSMContext):
    await state.update_data(ring_group="silver", ring_assay=message.text)
    await message.answer("Выберите сечение:", reply_markup=kb_ring_sections())
    await RingStates.section.set()

@dp.message_handler(lambda m: m.text in ["Полукруглое", "Прямоугольное"], state=RingStates.section)
async def ring_section(message: types.Message, state: FSMContext):
    await state.update_data(section=message.text)
    await message.answer("Внутренний диаметр (мм):")
    await RingStates.d_in.set()

@dp.message_handler(state=RingStates.d_in)
async def ring_d_in(message: types.Message, state: FSMContext):
    await state.update_data(d_in=parse_float(message.text))
    await message.answer("Ширина (мм):")
    await RingStates.width.set()

@dp.message_handler(state=RingStates.width)
async def ring_width(message: types.Message, state: FSMContext):
    await state.update_data(w=parse_float(message.text))
    await message.answer("Толщина (мм):")
    await RingStates.thickness.set()

@dp.message_handler(state=RingStates.thickness)
async def ring_thickness(message: types.Message, state: FSMContext):
    await state.update_data(t=parse_float(message.text))
    await message.answer("Цена за 1 г (руб). Если не надо — 0:")
    await RingStates.price.set()

@dp.message_handler(state=RingStates.price)
async def ring_price(message: types.Message, state: FSMContext):
    price = parse_float(message.text)
    data = await state.get_data()

    group, assay = data["ring_group"], data["ring_assay"]
    rho = metal_rho(group, assay)
    metal_str = f"{metal_title(group, assay)} (ρ={rho})"

    section = data["section"]
    d_in = float(data["d_in"])
    w = float(data["w"])
    t = float(data["t"])

    L_mm = ring_shank_length_mm(d_in, t)
    m_g = ring_weight_rect_g(rho, L_mm, w, t) if section == "Прямоугольное" else ring_weight_semiround_g(rho, L_mm, w, t)
    cost = m_g * price

    text = (
        f"💍 Результат (обручальное кольцо)\n\n"
        f"Металл: {metal_str}\n"
        f"Сечение: {section}\n\n"
        f"Длина шинки: {L_mm:.3f} мм\n"
        f"Вес кольца: {m_g:.2f} г\n"
        f"Стоимость металла: {cost:.2f} руб.\n"
    )

    await state.finish()
    await message.answer(text, reply_markup=kb_after_ring())

@dp.message_handler(lambda m: m.text == "💍 Еще одно кольцо", state="*")
async def ring_again(message: types.Message, state: FSMContext):
    await ring_entry(message, state)


# -------------------- TUBE FLOW --------------------

@dp.message_handler(lambda m: m.text == "Расчет трубки")
async def tube_entry(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Выберите режим диаметра:", reply_markup=kb_tube_modes())
    await TubeStates.mode.set()

@dp.message_handler(lambda m: m.text in ["Внешний диаметр", "Средний диаметр", "Внутренний диаметр"], state=TubeStates.mode)
async def tube_mode(message: types.Message, state: FSMContext):
    mode_map = {"Внешний диаметр": "outer", "Средний диаметр": "mid", "Внутренний диаметр": "inner"}
    await state.update_data(mode=mode_map[message.text])
    await message.answer("Диаметр трубки (мм):")
    await TubeStates.diameter.set()

@dp.message_handler(state=TubeStates.diameter)
async def tube_diameter(message: types.Message, state: FSMContext):
    diameter = parse_float(message.text)
    if diameter <= 0:
        return await message.reply("Введите число > 0.")
    await state.update_data(diameter=diameter)
    await message.answer("Толщина заготовки (мм):")
    await TubeStates.thickness.set()

@dp.message_handler(state=TubeStates.thickness)
async def tube_thickness(message: types.Message, state: FSMContext):
    thickness = parse_float(message.text)
    if thickness <= 0:
        return await message.reply("Введите число > 0.")

    data = await state.get_data()
    mode = data["mode"]
    diameter = float(data["diameter"])

    if mode == "outer" and diameter <= thickness:
        await state.finish()
        return await message.answer("Ошибка: для внешнего диаметра диаметр должен быть больше толщины.", reply_markup=kb_main())

    width = tube_blank_width(mode, thickness, diameter)
    width_out = round(width + 1e-12, 2)

    mode_text = {"outer": "Внешний диаметр", "mid": "Средний диаметр", "inner": "Внутренний диаметр"}[mode]
    text = (
        f"Расчет трубки\n\n"
        f"Режим: {mode_text}\n"
        f"Диаметр трубки: {diameter:.2f} мм\n"
        f"Толщина заготовки: {thickness:.2f} мм\n\n"
        f"Ширина заготовки: {width_out:.2f} мм\n"
    )

    await state.finish()
    await message.answer(text, reply_markup=kb_after_tube())

@dp.message_handler(lambda m: m.text == "Еще расчет трубки", state="*")
async def tube_again(message: types.Message, state: FSMContext):
    await tube_entry(message, state)


# -------------------- RUN --------------------

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)