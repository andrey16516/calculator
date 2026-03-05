import os
import math
from dataclasses import dataclass

from aiogram import Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile


# -------------------- METALS / ASSAYS --------------------
RHO_REF = 13.6

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
    model: str
    k_ref: float | None
    c_ref: float | None
    rigel_factor: float
    d_round_mode: str
    d_round_step: float
    D_round_mode: str
    D_round_step: float
    w_before_factor: float | None
    w_after_factor: float | None
    w_round_step: float | None


WEAVES: dict[str, WeaveCfg] = {
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


# -------------------- SOLDER --------------------
CLASSIC_850_PER_1G = {"Ag": 0.13, "Cu": 0.13, "Zn": 0.06, "Cd": 0.10}
REFRACTORY_850_PER_1G = {"Ag": 0.10, "Cu": 0.22, "Zn": 0.02}


# -------------------- RINGS --------------------
RING_SEMIROUND_K = 0.766


# -------------------- TUBE --------------------
def tube_blank_width(mode: str, thickness: float, diameter: float) -> float:
    if mode == "inner":
        return math.pi * (diameter + thickness)
    if mode == "outer":
        return math.pi * (diameter - thickness)
    return math.pi * diameter


# -------------------- UTIL --------------------
def file_near_script(filename: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)


def parse_float(text: str) -> float:
    return float(text.replace(",", ".").strip())


def floor_to_step(x: float, step: float) -> float:
    return math.floor(x / step) * step


def round_to_step(x: float, step: float) -> float:
    return round(x / step) * step


def apply_round(x: float, mode: str, step: float) -> float:
    return floor_to_step(x, step) if mode == "floor" else round_to_step(x, step)


def round2(x: float) -> float:
    return round(x + 1e-12, 2)


def fmt_g(x: float) -> str:
    return f"{round2(x):.2f}"


# -------------------- CALC --------------------
def d_emp_k(M: float, L: float, k: float) -> float:
    return math.sqrt((3.0 * M) / (k * L))


def d_emp_c(M: float, L: float, c: float) -> float:
    return math.sqrt(c * (M / L))


def calc_chain(rho: float, weave_key: str, L: float, M: float) -> dict:
    w = WEAVES[weave_key]
    if w.model == "emp_k":
        k = (w.k_ref or 0.0) * (rho / RHO_REF)
        d = d_emp_k(M, L, k)
    else:
        c = (w.c_ref or 0.0) * (RHO_REF / rho)
        d = d_emp_c(M, L, c)

    D = d * w.rigel_factor
    d_out = apply_round(d, w.d_round_mode, w.d_round_step)
    D_out = apply_round(D, w.D_round_mode, w.D_round_step)

    out = {"d": d_out, "D": D_out}
    if w.w_before_factor and w.w_after_factor and w.w_round_step:
        out["w_before"] = apply_round(D_out * w.w_before_factor, "round", w.w_round_step)
        out["w_after"] = apply_round(D_out * w.w_after_factor, "round", w.w_round_step)
    return out


def scale_recipe(recipe: dict, grams: float) -> dict:
    return {k: recipe[k] * grams for k in recipe}


def ring_shank_length_mm(d_in_mm: float, t_mm: float) -> float:
    return math.pi * (d_in_mm + t_mm)


def ring_weight_rect_g(rho: float, L_mm: float, w_mm: float, t_mm: float) -> float:
    return rho * ((w_mm * t_mm * L_mm) / 1000.0)


def ring_weight_semiround_g(rho: float, L_mm: float, w_mm: float, t_mm: float) -> float:
    return rho * ((RING_SEMIROUND_K * w_mm * t_mm * L_mm) / 1000.0)


# -------------------- KEYBOARDS --------------------
def kb_main():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧮 Расчет цепи")],
            [KeyboardButton(text="🧪 Припой")],
            [KeyboardButton(text="💍 Расчет обручальных колец")],
            [KeyboardButton(text="Расчет трубки")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_chain_metals():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Золото 585"), KeyboardButton(text="Серебро 925")],
            [KeyboardButton(text="Золото другая проба"), KeyboardButton(text="Серебро другая проба")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_gold_assays():
    rows = []
    assays = list(GOLD_ASSAYS.keys())
    for i in range(0, len(assays), 2):
        rows.append([KeyboardButton(text=a) for a in assays[i:i + 2]])
    rows.append([KeyboardButton(text="❌ Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_silver_assays():
    rows = []
    assays = list(SILVER_ASSAYS.keys())
    for i in range(0, len(assays), 2):
        rows.append([KeyboardButton(text=a) for a in assays[i:i + 2]])
    rows.append([KeyboardButton(text="❌ Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_weaves():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Бисмарк"), KeyboardButton(text="Московский бисмарк")],
            [KeyboardButton(text="Московский бит"), KeyboardButton(text="Рамзес")],
            [KeyboardButton(text="Американка"), KeyboardButton(text="Лисий хвост (византия)")],
            [KeyboardButton(text="Якорное"), KeyboardButton(text="Панцирное")],
            [KeyboardButton(text="Шопард")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_after_chain():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔁 Повторить такую же цепь")],
            [KeyboardButton(text="🧮 Новый расчет")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_solder_gold_types():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Классический"), KeyboardButton(text="Тугоплавкий")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_solder_assay_850():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="850 проба")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_after_solder():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Еще раз припой")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_ring_sections():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Полукруглое"), KeyboardButton(text="Прямоугольное")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_after_ring():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💍 Еще одно кольцо")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_tube_modes():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Внешний диаметр"), KeyboardButton(text="Средний диаметр"), KeyboardButton(text="Внутренний диаметр")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


def kb_after_tube():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Еще расчет трубки")],
            [KeyboardButton(text="🏠 В меню")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )


# -------------------- FSM STATES --------------------
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
    section = State()
    d_in = State()
    width = State()
    thickness = State()
    price = State()


class TubeStates(StatesGroup):
    mode = State()
    diameter = State()
    thickness = State()


# -------------------- ROUTER --------------------
router = Router()


# -------------------- HANDLERS COMMON --------------------
@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Ювелирный калькулятор", reply_markup=kb_main())


@router.message(F.text == "❌ Отмена")
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=kb_main())


@router.message(F.text == "🏠 В меню")
async def to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню:", reply_markup=kb_main())


# -------------------- CHAINS --------------------
@router.message(F.text == "🧮 Расчет цепи")
async def chains_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(chain_group=DEFAULT_CHAIN_METAL[0], chain_assay=DEFAULT_CHAIN_METAL[1])
    await message.answer("Выберите металл/пробу:", reply_markup=kb_chain_metals())
    await state.set_state(ChainStates.choosing_metal)


@router.message(ChainStates.choosing_metal, F.text == "Золото 585")
async def chains_gold_585(message: Message, state: FSMContext):
    await state.update_data(chain_group="gold", chain_assay="585")
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await state.set_state(ChainStates.weave)


@router.message(ChainStates.choosing_metal, F.text == "Серебро 925")
async def chains_silver_925(message: Message, state: FSMContext):
    await state.update_data(chain_group="silver", chain_assay="925")
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await state.set_state(ChainStates.weave)


@router.message(ChainStates.choosing_metal, F.text == "Золото другая проба")
async def chains_gold_other(message: Message, state: FSMContext):
    await message.answer("Выберите пробу золота:", reply_markup=kb_gold_assays())
    await state.set_state(ChainStates.choosing_gold_assay)


@router.message(ChainStates.choosing_gold_assay, F.text.in_(list(GOLD_ASSAYS.keys())))
async def chains_gold_assay_selected(message: Message, state: FSMContext):
    await state.update_data(chain_group="gold", chain_assay=message.text)
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await state.set_state(ChainStates.weave)


@router.message(ChainStates.choosing_metal, F.text == "Серебро другая проба")
async def chains_silver_other(message: Message, state: FSMContext):
    await message.answer("Выберите пробу серебра:", reply_markup=kb_silver_assays())
    await state.set_state(ChainStates.choosing_silver_assay)


@router.message(ChainStates.choosing_silver_assay, F.text.in_(list(SILVER_ASSAYS.keys())))
async def chains_silver_assay_selected(message: Message, state: FSMContext):
    await state.update_data(chain_group="silver", chain_assay=message.text)
    await message.answer("Выберите плетение:", reply_markup=kb_weaves())
    await state.set_state(ChainStates.weave)


@router.message(ChainStates.weave, F.text.in_(list(WEAVES.keys())))
async def chains_choose_weave(message: Message, state: FSMContext):
    weave_key = message.text
    await state.update_data(weave=weave_key)

    fname = PHOTO_FILES.get(weave_key)
    if fname:
        path = file_near_script(fname)
        if os.path.exists(path):
            try:
                await message.answer_photo(FSInputFile(path), caption=f"Плетение: {WEAVES[weave_key].ui_name}")
            except Exception:
                pass

    await message.answer("Введите длину изделия (см):")
    await state.set_state(ChainStates.length)


@router.message(F.text == "🧮 Новый расчет")
async def chains_new_calc(message: Message, state: FSMContext):
    await chains_entry(message, state)


@router.message(ChainStates.after, F.text == "🔁 Повторить такую же цепь")
async def chains_repeat(message: Message, state: FSMContext):
    data = await state.get_data()
    weave_key = data.get("weave")
    await message.answer(f"Повтор: {WEAVES[weave_key].ui_name}\nВведите длину изделия (см):")
    await state.set_state(ChainStates.length)


@router.message(ChainStates.length)
async def chains_length(message: Message, state: FSMContext):
    try:
        L_total = parse_float(message.text)
        if L_total <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите корректную длину (например 55).")

    await state.update_data(L_total=L_total)
    await message.answer("Введите массу изделия (г):")
    await state.set_state(ChainStates.mass)


@router.message(ChainStates.mass)
async def chains_mass(message: Message, state: FSMContext):
    try:
        M_total = parse_float(message.text)
        if M_total <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите корректную массу (например 20).")

    await state.update_data(M_total=M_total)
    await message.answer("Длина замка + концевиков (см). Если нет — 0:")
    await state.set_state(ChainStates.lock_len)


@router.message(ChainStates.lock_len)
async def chains_lock_len(message: Message, state: FSMContext):
    try:
        L_lock = parse_float(message.text)
        if L_lock < 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число >= 0.")

    await state.update_data(L_lock=L_lock)

    if abs(L_lock) < 1e-12:
        await state.update_data(M_lock=0.0)
        return await chains_finish_calc(message, state)

    await message.answer("Масса замка + концевиков (г):")
    await state.set_state(ChainStates.lock_mass)


@router.message(ChainStates.lock_mass)
async def chains_lock_mass(message: Message, state: FSMContext):
    try:
        M_lock = parse_float(message.text)
        if M_lock < 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число >= 0.")

    await state.update_data(M_lock=M_lock)
    await chains_finish_calc(message, state)


async def chains_finish_calc(message: Message, state: FSMContext):
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
            await state.clear()
            return await message.answer("Ошибка: длина замка больше/равна длине изделия.", reply_markup=kb_main())
        if M_weave <= 0:
            await state.clear()
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
    await state.set_state(ChainStates.after)


# -------------------- SOLDER --------------------
@router.message(F.text == "🧪 Припой")
async def solder_entry(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Припой (золото). Выберите тип:", reply_markup=kb_solder_gold_types())
    await state.set_state(SolderStates.choosing_type)


@router.message(SolderStates.choosing_type, F.text.in_(["Классический", "Тугоплавкий"]))
async def solder_choose_type(message: Message, state: FSMContext):
    await state.update_data(solder_type=message.text)
    await message.answer("Выберите пробу исходного металла:", reply_markup=kb_solder_assay_850())
    await state.set_state(SolderStates.choosing_assay)


@router.message(SolderStates.choosing_assay, F.text == "850 проба")
async def solder_choose_assay(message: Message, state: FSMContext):
    await message.answer("Сколько грамм пересчитать? (например 1 или 0.5)")
    await state.set_state(SolderStates.waiting_grams)


@router.message(SolderStates.waiting_grams)
async def solder_grams(message: Message, state: FSMContext):
    try:
        grams = parse_float(message.text)
        if grams <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число > 0 (например 1 или 0.5).")

    data = await state.get_data()
    stype = data.get("solder_type")
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

    await state.clear()
    await message.answer("\n".join(lines), reply_markup=kb_after_solder())


@router.message(F.text == "🧪 Еще раз припой")
async def solder_again(message: Message, state: FSMContext):
    await solder_entry(message, state)


# -------------------- RINGS --------------------
@router.message(F.text == "💍 Расчет обручальных колец")
async def ring_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(ring_group=DEFAULT_RING_METAL[0], ring_assay=DEFAULT_RING_METAL[1])
    await message.answer("Выберите металл/пробу:", reply_markup=kb_chain_metals())
    await state.set_state(RingStates.choosing_metal)


@router.message(RingStates.choosing_metal, F.text == "Золото 585")
async def ring_gold_585(message: Message, state: FSMContext):
    await state.update_data(ring_group="gold", ring_assay="585")
    await message.answer("Выберите сечение:", reply_markup=kb_ring_sections())
    await state.set_state(RingStates.section)


@router.message(RingStates.choosing_metal, F.text == "Серебро 925")
async def ring_silver_925(message: Message, state: FSMContext):
    await state.update_data(ring_group="silver", ring_assay="925")
    await message.answer("Выберите сечение:", reply_markup=kb_ring_sections())
    await state.set_state(RingStates.section)


@router.message(RingStates.section, F.text.in_(["Полукруглое", "Прямоугольное"]))
async def ring_section(message: Message, state: FSMContext):
    await state.update_data(section=message.text)
    await message.answer("Внутренний диаметр (мм):")
    await state.set_state(RingStates.d_in)


@router.message(RingStates.d_in)
async def ring_d_in(message: Message, state: FSMContext):
    try:
        d_in = parse_float(message.text)
        if d_in <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число > 0.")

    await state.update_data(d_in=d_in)
    await message.answer("Ширина (мм):")
    await state.set_state(RingStates.width)


@router.message(RingStates.width)
async def ring_width(message: Message, state: FSMContext):
    try:
        w = parse_float(message.text)
        if w <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число > 0.")

    await state.update_data(w=w)
    await message.answer("Толщина (мм):")
    await state.set_state(RingStates.thickness)


@router.message(RingStates.thickness)
async def ring_thickness(message: Message, state: FSMContext):
    try:
        t = parse_float(message.text)
        if t <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число > 0.")

    await state.update_data(t=t)
    await message.answer("Цена за 1 г (руб). Если не надо — 0:")
    await state.set_state(RingStates.price)


@router.message(RingStates.price)
async def ring_price(message: Message, state: FSMContext):
    try:
        price = parse_float(message.text)
        if price < 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число >= 0.")

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
    await state.clear()
    await message.answer(text, reply_markup=kb_after_ring())


@router.message(F.text == "💍 Еще одно кольцо")
async def ring_again(message: Message, state: FSMContext):
    # FIX: handle "Еще одно кольцо" button
    await ring_entry(message, state)


# -------------------- TUBE --------------------
@router.message(F.text == "Расчет трубки")
async def tube_entry(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите режим диаметра:", reply_markup=kb_tube_modes())
    await state.set_state(TubeStates.mode)


@router.message(TubeStates.mode, F.text.in_(["Внешний диаметр", "Средний диаметр", "Внутренний диаметр"]))
async def tube_mode(message: Message, state: FSMContext):
    mode_map = {"Внешний диаметр": "outer", "Средний диаметр": "mid", "Внутренний диаметр": "inner"}
    await state.update_data(mode=mode_map[message.text])
    await message.answer("Диаметр трубки (мм):")
    await state.set_state(TubeStates.diameter)


@router.message(TubeStates.diameter)
async def tube_diameter(message: Message, state: FSMContext):
    try:
        diameter = parse_float(message.text)
        if diameter <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число > 0.")

    await state.update_data(diameter=diameter)
    await message.answer("Толщина заготовки (мм):")
    await state.set_state(TubeStates.thickness)


@router.message(TubeStates.thickness)
async def tube_thickness(message: Message, state: FSMContext):
    try:
        thickness = parse_float(message.text)
        if thickness <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите число > 0.")

    data = await state.get_data()
    mode = data["mode"]
    diameter = float(data["diameter"])

    if mode == "outer" and diameter <= thickness:
        await state.clear()
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

    await state.clear()
    await message.answer(text, reply_markup=kb_after_tube())


@router.message(F.text == "Еще расчет трубки")
async def tube_again(message: Message, state: FSMContext):
    await tube_entry(message, state)


# -------------------- DISPATCHER FACTORY --------------------
def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    return dp