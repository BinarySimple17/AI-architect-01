import csv
import random
from datetime import datetime, timedelta

# ------------------------------
# Параметры генерации
# ------------------------------
CITIES = ["Москва", "Волгоград", "Санкт-Петербург", "Воркута", "Иркутск"]

AIRLINES = {
    "Аэрофлот": (1000, 1999),
    "S7 Airlines": (2000, 2999),
    "Победа": (3000, 3999),
    "ЮТэйр": (4000, 4999),
    "Россия": (5000, 5999),
    "Нордвинд": (6000, 6999),
    "Уральские авиалинии": (7000, 7999),
    "Red Wings": (8000, 8999),
}

# Диапазон дат – весь 2026 год
START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 12, 31)

PRICE_RANGE = (2500, 19500)


def random_date_2026():
    """Случайная дата в пределах 2026 года"""
    delta = END_DATE - START_DATE
    random_days = random.randint(0, delta.days)
    return (START_DATE + timedelta(days=random_days)).strftime("%Y-%m-%d")


def random_flight_number(airline):
    low, high = AIRLINES[airline]
    return f"{airline[:2].upper()}{random.randint(low, high)}"


def random_price():
    return random.randint(*PRICE_RANGE)


# ------------------------------
# Генерация маршрутов
# ------------------------------
rows = []

# 1. Прямые рейсы Москва -> Волгоград (40 штук)
for _ in range(40):
    airline = random.choice(list(AIRLINES.keys()))
    rows.append(
        {
            "line": airline,
            "flight": random_flight_number(airline),
            "departure": "Москва",
            "arrival": "Волгоград",
            "departure_date": random_date_2026(),
            "price": random_price(),
        }
    )

# 2. Пересадочные маршруты Волгоград -> Воркута (60 пар = 120 рейсов)
intermediate_cities = [
    c for c in CITIES if c not in ("Волгоград", "Воркута")
]  # Москва, СПб, Иркутск
for _ in range(60):
    x = random.choice(intermediate_cities)
    # Сегмент 1: Волгоград -> X
    airline1 = random.choice(list(AIRLINES.keys()))
    rows.append(
        {
            "line": airline1,
            "flight": random_flight_number(airline1),
            "departure": "Волгоград",
            "arrival": x,
            "departure_date": random_date_2026(),
            "price": random_price(),
        }
    )
    # Сегмент 2: X -> Воркута
    airline2 = random.choice(list(AIRLINES.keys()))
    rows.append(
        {
            "line": airline2,
            "flight": random_flight_number(airline2),
            "departure": x,
            "arrival": "Воркута",
            "departure_date": random_date_2026(),
            "price": random_price(),
        }
    )

# 3. Остальные случайные рейсы (300 - 40 - 120 = 140)
remaining = 300 - len(rows)
for _ in range(remaining):
    dep, arr = random.sample(CITIES, 2)
    airline = random.choice(list(AIRLINES.keys()))
    rows.append(
        {
            "line": airline,
            "flight": random_flight_number(airline),
            "departure": dep,
            "arrival": arr,
            "departure_date": random_date_2026(),
            "price": random_price(),
        }
    )

# Перемешиваем все строки
random.shuffle(rows)

# Запись в CSV
with open("data/flights.csv", "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "line",
            "flight",
            "departure",
            "arrival",
            "departure_date",
            "price",
        ],
        delimiter=";",
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"✅ Сгенерировано {len(rows)} рейсов в файл flights.csv (все даты — 2026 год)")
