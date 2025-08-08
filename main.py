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
    df_stones = pd.read_excel("таблица_обновленная.xlsx")
    df_stones.columns = df_stones.columns.str.strip()
    df_stones["Длина"] = pd.to_numeric(df_stones["Длина"], errors="coerce")
    df_stones["Ширина"] = pd.to_numeric(df_stones["Ширина"], errors="coerce")
    df_stones["Высота"] = pd.to_numeric(df_stones["Высота"], errors="coerce")
    df_stones["Вес сброса"] = pd.to_numeric(df_stones["Вес сброса"], errors="coerce")
except Exception as e:
    print("❌ Ошибка загрузки таблицы:", e)
    df_stones = pd.DataFrame()

# Плотности
DENSITY_MAP = {
    "рубин": 4.0, "розовый рубин": 4.0, "аметист": 2.65, "топаз": 3.5, "гранат": 3.95,
    "хризолит": 3.3, "циркон": 4.6, "шпинель": 3.6, "турмалин": 3.1, "аквамарин": 2.7,
    "изумруд": 2.8, "гематит": 5.2, "кварц": 2.65, "обсидиан": 2.4, "жемчуг": 2.7,
    "малахит": 4.0, "сапфир": 4.0, "флюорит": 3.2, "гагат": 1.3, "пластик": 1.2,
    "металл": 8.0, "стекло": 2.5, "эмаль": 2.3, "неизвестно": 2.5
}

SHAPE_COEFFS = {
    "круг": 0.0018, "овал": 0.0017, "удлиненный овал": 0.00165, "маркиз": 0.0016,
    "прямоугольник": 0.0015, "квадрат": 0.0016, "груша": 0.0016, "сердце": 0.00155
}

def extract_dimensions(text):
    numbers = [float(n.replace(",", ".")) for n in re.findall(r"(\d+(?:[.,]\d+)?)", text)]
    if len(numbers) >= 2:
        length, width = numbers[0], numbers[1]
        height = numbers[2] if len(numbers) >= 3 else None
        return length, width, height
    return None, None, None

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

def normalize_shape(vision_shape):
    if not vision_shape:
        return None
    vision_shape = vision_shape.lower()
    known_shapes = df_stones["Форма"].dropna().unique()
    for shape in known_shapes:
        if shape.lower() in vision_shape or vision_shape in shape.lower():
            return shape
    return vision_shape

def normalize_stone_type(vision_type):
    if not vision_type:
        return None

    vision_type = vision_type.lower().strip()

    # Простейшие перехваты по ключевым словам
    synonyms = {
        "розов": "рубин",
        "спессартин": "гранат",
        "голубой топаз": "топаз",
        "дымчатый кварц": "кварц",
        "горный хрусталь": "кварц",
    }
    for key, val in synonyms.items():
        if key in vision_type:
            print(f"🔁 Перехват ({key}): '{vision_type}' → '{val}'")
            vision_type = val
            break

    known_types = df_stones["Название"].dropna().unique()
    lower_map = {t.lower(): t for t in known_types}
    import difflib
    match = difflib.get_close_matches(vision_type, lower_map.keys(), n=1, cutoff=0.6)
    if match:
        return lower_map[match[0]]

    return vision_type




def find_closest_stone(length, width, height=None, shape=None, stone_type=None, tolerance=2.0):
    if df_stones.empty:
        return None

    df_filtered = df_stones.copy()

    if shape:
        df_filtered = df_filtered[df_filtered["Форма"].str.lower().str.contains(shape.lower())]
    if stone_type:
        df_filtered = df_filtered[df_filtered["Название"].str.lower().str.contains(stone_type.lower())]

    delta = (df_filtered["Длина"] - length) ** 2 + (df_filtered["Ширина"] - width) ** 2
    if height is not None:
        delta += (df_filtered["Высота"] - height) ** 2
    df_filtered["delta"] = delta ** 0.5
    df_nearest = df_filtered[df_filtered["delta"] <= tolerance].sort_values(by="delta")

    if not df_nearest.empty:
        best = df_nearest.iloc[0]
        if height is not None and not pd.isna(best["Высота"]):
            ref_volume = best["Длина"] * best["Ширина"] * best["Высота"]
            volume = length * width * height
        else:
            ref_volume = best["Длина"] * best["Ширина"]
            volume = length * width
        ratio = volume / ref_volume
        corrected_weight = round(best["Вес сброса"] * ratio, 2)
        return {
            "Вид": best["Название"],
            "Форма": best["Форма"],
            "Размер": f"{best['Длина']} × {best['Ширина']} × {best['Высота']} мм",
            "Вес": corrected_weight
        }
    return None

def estimate_weight(length, width, height, shape, stone_type):
    density = DENSITY_MAP.get(stone_type, DENSITY_MAP["неизвестно"])
    coeff = SHAPE_COEFFS.get(shape, 0.0016)
    if length is None or width is None:
        return 0.0
    volume = coeff * length * width
    if height:
        volume *= height
    return round(volume * density, 2)

def identify_stone_with_vision(image_url):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Ты эксперт-геммолог. Определи вид и форму камня. Ответ строго в формате: Вид: ...\nФорма: ...\nАльтернатива: ..."
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
            length, width, height = extract_dimensions(caption)
            file_url = get_file_url(file_id)

            stone_info = None
            vision_result = identify_stone_with_vision(file_url)

            shape = stone_type = None
            if vision_result:
                for line in vision_result.splitlines():
                    if line.lower().startswith("форма"):
                        raw_shape = line.split(":", 1)[-1].strip()
                        shape = normalize_shape(raw_shape)
                    elif line.lower().startswith("вид"):
                        raw_type = line.split(":", 1)[-1].strip()
                        stone_type = normalize_stone_type(raw_type)

            if height:
                size_text = f"{length} × {width} × {height} мм"
            else:
                size_text = f"{length} × {width} мм"
            response_text = f"📏 Размер: {size_text}\n"

            if length and width:
                stone_info = find_closest_stone(length, width, height, shape, stone_type)
                if stone_info:
                    response_text += (
                        f"⚖️ Вес: ~{stone_info['Вес']} г\n"
                        f"📐 Форма: {stone_info['Форма']}\n"
                    )
                elif shape and stone_type:
                    weight = estimate_weight(length, width, height, shape.lower(), stone_type.lower())
                    response_text += (
                        f"⚖️ ~Вес по формуле: {weight} г\n"
                        f"📐 Форма: {shape}\n"
                    )

            if vision_result:
                response_text += f"\n🧠 Vision:\n{vision_result}"

            send_message(chat_id, response_text)

        else:
            send_message(chat_id, "📷 Пришли фото камня с размерами в подписи.")

    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)









