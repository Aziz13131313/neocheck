from flask import Flask, request
import requests
import re
import openai
import pandas as pd
from math import pi
import os

client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

TELEGRAM_TOKEN = "7743518282:AAEQ29yMWS19-Tb4NTu5p02Rh68iI0cYziE"
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

ALL_DENSITIES = {
    "Аквамарин": 2.7, "Агат": 2.6, "Жемчуг": 2.7, "Гагат": 1.3, "Гематит": 5.3, "Малахит": 4.0,
    "Дымчатый кварц": 2.65, "Александрит": 3.68, "Аметист": 2.65, "Циркон": 4.6, "Хрусталь": 2.65,
    "Топаз": 3.5, "Рубин": 4.0, "Сапфир": 4.0, "Изумруд": 2.7, "Стекло": 2.5, "Пластик": 1.2,
    "Эмаль": 2.3, "Металл": 8.0, "Флюорит": 3.18, "Гранат": 4.1, "Фианит": 5.5, "Хризолит": 3.3,
    "Перламутр": 2.7, "Клевер": 2.7, "Четырехлистник": 2.7, "Пятилистник": 2.7, "Шестилистник": 2.7
}

NORMALIZED_FORMS = {
    f.strip().lower(): f.strip().lower() for f in [
        'груша', 'кабошон', 'кабошон овал', 'кабошон капля', 'кабошон квадрат', 'кабошон круг',
        'кабошон маркиз', 'кабошон овал', 'кабошон прямоугольник', 'кабошон сердце', 'кабошон сфера',
        'кабошон удлиненный овал', 'кабюшон', 'капля', 'квадрат', 'клевер', 'круг', 'маркиз',
        'овал', 'овал удлиненный', 'полукруг', 'прямоугольник', 'прямоугольник удлиненный', 'пятилистник',
        'ромб', 'сердце', 'сфера', 'треугольник', 'удлиненный овал', 'фантазия', 'цветок',
        'цветочник', 'четырехлистник', 'шестилистник', 'шар'
    ]
}

app = Flask(__name__)

try:
    df_stones = pd.read_excel("таблица новая123.xlsx")
    df_stones["Длина"] = pd.to_numeric(df_stones["Длина"], errors="coerce")
    df_stones["Ширина"] = pd.to_numeric(df_stones["Ширина"], errors="coerce")
    df_stones["Вес сброса"] = pd.to_numeric(df_stones["Вес сброса"], errors="coerce")
    df_stones["Высота"] = pd.to_numeric(df_stones["Высота"], errors="coerce")
    df_stones["Форма"] = df_stones["Форма"].astype(str).str.lower().str.strip()
    df_stones["Название"] = df_stones["Название"].astype(str).str.capitalize().str.strip()
except Exception as e:
    print("❌ Ошибка загрузки таблицы:", e)
    df_stones = pd.DataFrame()

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
        return None

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def identify_stone_with_vision(image_url):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": (
                    "Ты эксперт-геммолог. Игнорируй пальцы, тени и фон. Ответь строго в этом формате, без пояснений и лишнего текста:\n"
                    "Вид: [Название]\nАльтернатива: [Альтернатива]\nФорма: [Форма]"
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": "Что за камень на фото?"},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]}
            ],
            max_tokens=300
        )
        result = response.choices[0].message.content.strip()
        return result
    except Exception as e:
        print("❌ Ошибка Vision:", e)
        return None

def normalize_form(f):
    f = f.strip().lower()
    return NORMALIZED_FORMS.get(f, f)

def find_closest_stone(length, width, form, stone_type):
    form = normalize_form(form)
    df_filtered = df_stones[(df_stones["Форма"] == form) & (df_stones["Название"] == stone_type)]
    df_filtered = df_filtered.copy()
    df_filtered["delta"] = ((df_filtered["Длина"] - length)**2 + (df_filtered["Ширина"] - width)**2)**0.5
    df_nearest = df_filtered[df_filtered["delta"] <= 3.0].sort_values(by="delta")
    if not df_nearest.empty:
        best = df_nearest.iloc[0]
        delta = best["delta"]
        correction = min(0.1 * delta, 0.15)
        if delta < 1:
            weight = best["Вес сброса"]
        elif length > best["Длина"] or width > best["Ширина"]:
            weight = round(best["Вес сброса"] * (1 + correction), 2)
        else:
            weight = round(best["Вес сброса"] * (1 - correction), 2)
        return best["Длина"], best["Ширина"], best["Высота"], weight
    return None

@app.route("/", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        caption = msg.get("caption", "")
        length, width = extract_dimensions(caption)
        file_id = msg["photo"][-1]["file_id"]
        url = get_file_url(file_id)
        vision = identify_stone_with_vision(url) or ""

        stone_type = re.search(r"Вид[:\s]+(.+)", vision)
        form = re.search(r"Форма[:\s]+(.+)", vision)
        stone_type = stone_type.group(1).strip().capitalize() if stone_type else None
        form = normalize_form(form.group(1).strip()) if form else None

        density = ALL_DENSITIES.get(stone_type)
        response = ""

        if length and width and form and stone_type and density:
            if form in ["шар", "сфера", "кабошон сфера"]:
                radius = length / 2
                volume = (4/3) * pi * radius ** 3
                height = length
            elif form in ["клевер", "четырехлистник", "пятилистник", "шестилистник"]:
                height = 2.0
                volume = (pi * length * width * height) / 6
            else:
                result = find_closest_stone(length, width, form, stone_type)
                if result:
                    l, w, h, weight = result
                    response += f"📏 {l}×{w}×{h} мм\n⚖️ ~{weight} г\nФорма: {form}\n"
                    send_message(chat_id, response + "\n🧠 Vision:\n" + vision)
                    return "ok"
                height = (length + width) / 4
                volume = (pi * length * width * height) / 6
            weight = round(volume * density / 1000, 2)
            response += f"📏 {length}×{width}×{round(height,2)} мм\n⚖️ ~{weight} г\nФорма: {form}\n"
        else:
            response = "❌ Не удалось определить вид, форму или плотность."

        response += "\n🧠 Vision:\n" + vision
        send_message(chat_id, response)
    return "ok"

@app.route("/")
def index():
    return "✅ Бот работает", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)








