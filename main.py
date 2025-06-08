from flask import Flask, request
import requests
import os
import re
import openai
import pandas as pd

# Конфигурация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)

# Загрузка Excel-таблицы
try:
    df_stones = pd.read_excel("таблица новая123.xlsx")
    df_stones["Длина"] = pd.to_numeric(df_stones["Длина"], errors="coerce")
    df_stones["Ширина"] = pd.to_numeric(df_stones["Ширина"], errors="coerce")
    df_stones["Высота"] = pd.to_numeric(df_stones["Высота"], errors="coerce")
    df_stones["Вес сброса"] = pd.to_numeric(df_stones["Вес сброса"], errors="coerce")
    df_stones["Форма"] = df_stones["Форма"].astype(str).str.strip().str.lower()
except Exception as e:
    print("❌ Ошибка загрузки таблицы:", e)
    df_stones = pd.DataFrame()

# Плотности
DENSITY_MAP = {
    "Рубин": 4.0, "Аметист": 2.65, "Топаз": 3.5, "Гранат": 3.95, "Хризолит": 3.3,
    "Циркон": 4.6, "Шпинель": 3.6, "Турмалин": 3.1, "Аквамарин": 2.7, "Изумруд": 2.8,
    "Гематит": 5.2, "Кварц": 2.65, "Кварц дымчатый": 2.65, "Обсидиан": 2.4,
    "Стекло": 2.5, "Неизвестно": 2.5, "Жемчуг": 2.7, "Гагат": 1.3, "Фианит": 5.5,
    "Флюорит": 3.18, "Малахит": 4.0, "Перламутр": 2.7, "Пластик": 1.2, "Металл": 8.0
}

SHAPE_COEFFS = {
    "круг": 0.0018, "овал": 0.0017, "удлиненный овал": 0.00165, "маркиз": 0.0016,
    "прямоугольник": 0.0015, "квадрат": 0.0016, "груша": 0.0016, "сердце": 0.00155,
    "клевер": 0.0015, "четырехлистник": 0.0015, "пятилистник": 0.0015, "шестилистник": 0.0015
}

SHAPE_ALIASES = {
    "четырёхлепестковая": "четырехлистник",
    "четырёхлистник": "четырехлистник",
    "клевер": "четырехлистник",
    "удлинённый прямоугольник": "прямоугольник",
    "кабошон овал": "овал",
    "кабошон круг": "круг",
    "кабошон квадрат": "квадрат",
    "кабошон": "круг",
    "багет": "прямоугольник"
}

def normalize_shape(shape):
    shape = shape.strip().lower()
    return SHAPE_ALIASES.get(shape, shape)

def extract_dimensions(text):
    numbers = re.findall(r"(\d+(?:[.,]\d+)?)", text)
    if len(numbers) >= 2:
        return float(numbers[0].replace(",", ".")), float(numbers[1].replace(",", "."))
    return None, None

def get_file_url(file_id):
    res = requests.get(f"{TELEGRAM_URL}/getFile?file_id={file_id}")
    try:
        path = res.json()["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}"
    except KeyError:
        print("⚠️ Ошибка получения file_path", res.text)
        return None

def send_message(chat_id, text):
    print("📤 Ответ:", text)
    requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def find_closest_stone(length, width, shape=None, stone_type=None, tolerance=2.0):
    if df_stones.empty:
        return None

    df_filtered = df_stones.copy()
    if shape:
        df_filtered = df_filtered[df_filtered["Форма"] == shape]
    if stone_type:
        df_filtered = df_filtered[df_filtered["Название"].str.lower().str.contains(stone_type.lower())]

    df_filtered["delta"] = ((df_filtered["Длина"] - length) ** 2 + (df_filtered["Ширина"] - width) ** 2) ** 0.5
    df_nearest = df_filtered[df_filtered["delta"] <= tolerance].sort_values(by="delta")

    if not df_nearest.empty:
        best = df_nearest.iloc[0]
        delta_weight = best["delta"] * 0.1
        corrected_weight = round(best["Вес сброса"] - delta_weight, 2)
        return {
            "Вид": best["Название"],
            "Форма": best["Форма"],
            "Размер": f"{best['Длина']} × {best['Ширина']} × {best['Высота']} мм",
            "Вес": corrected_weight
        }
    return None

def estimate_weight(length, width, shape, stone_type):
    shape = normalize_shape(shape)
    density = DENSITY_MAP.get(stone_type, 2.5)

    if shape in ["клевер", "четырехлистник", "пятилистник", "шестилистник"]:
        height = 2.0
        coeff = SHAPE_COEFFS.get(shape, 0.0015)
        volume = coeff * length * width * height
    elif shape in ["шар", "сфера"]:
        height = length
        volume = (4/3) * 3.1416 * (length / 2) ** 3
    else:
        coeff = SHAPE_COEFFS.get(shape, 0.0016)
        volume = coeff * length * width

    return round(volume * density, 2)

def identify_stone_with_vision(image_url):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Ты эксперт-геммолог. Определи вид и форму камня. Ответ дай строго в формате: Вид: ...\nФорма: ...\nАльтернатива: ..."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Что это за камень?"},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("❌ Ошибка Vision:", e)
        return None

@app.route("/", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    print("📩 Пришло сообщение:", data)

    if "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]

        if "photo" in message:
            file_id = message["photo"][-1]["file_id"]
            caption = message.get("caption", "")
            length, width = extract_dimensions(caption)
            file_url = get_file_url(file_id)

            stone_info = None
            vision_result = identify_stone_with_vision(file_url)

            shape = stone_type = None
            if vision_result:
                for line in vision_result.splitlines():
                    if line.lower().startswith("форма"):
                        shape = normalize_shape(line.split(":", 1)[-1].strip())
                    elif line.lower().startswith("вид"):
                        stone_type = line.split(":", 1)[-1].strip()

            if length and width:
                stone_info = find_closest_stone(length, width, shape, stone_type)

            response_text = f"📏 Размер: {length} × {width} мм\n"

            if stone_info:
                response_text += (
                    f"⚖️ Вес: ~{stone_info['Вес']} г\n"
                    f"📐 Форма: {stone_info['Форма']}\n"
                )
            else:
                if length and width and shape and stone_type:
                    weight = estimate_weight(length, width, shape, stone_type)
                    response_text += (
                        f"⚖️ ~Вес по формуле: {weight} г\n"
                        f"📐 Форма: {shape}\n"
                    )

            if vision_result:
                response_text += f"🧠 Vision:\n{vision_result}"

            send_message(chat_id, response_text)

        else:
            send_message(chat_id, "📷 Пришли фото камня с размерами в подписи.")

    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)











