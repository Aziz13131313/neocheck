from flask import Flask, request
import requests
import re
import openai
import pandas as pd
from math import pi

ALL_DENSITIES = {
    "Аквамарин": 2.7, "Агат": 2.6, "Жемчуг": 2.7, "Гагат": 1.3, "Гематит": 5.3, "Малахит": 4.0,
    "Дымчатый кварц": 2.65, "Александрит": 3.68, "Аметист": 2.65, "Циркон": 4.6, "Хрусталь": 2.65,
    "Топаз": 3.5, "Рубин": 4.0, "Сапфир": 4.0, "Изумруд": 2.7, "Стекло": 2.5, "Пластик": 1.2,
    "Эмаль": 2.3, "Металл": 8.0, "Флюорит": 3.18, "Гранат": 4.1, "Фианит": 5.5, "Хризолит": 3.3,
    "Четырёхлистник": 2.7, "Пятилучевая": 2.7, "Перламутр": 2.7
}

TELEGRAM_TOKEN = "7743518282:AAEQ29yMWS19-Tb4NTu5p02Rh68iI0cYziE"
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_API_KEY = "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"

client = openai.OpenAI(api_key=OPENAI_API_KEY)
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

def extract_manual_type(text):
    match = re.search(r"Вид[:\s]+([А-Яа-яA-Za-z-\s]+)", text)
    return match.group(1).strip() if match else None

def get_file_url(file_id):
    res = requests.get(f"{TELEGRAM_URL}/getFile?file_id={file_id}")
    try:
        path = res.json()["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}"
    except KeyError:
        return None

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def find_closest_stone(length, width, form, stone_type):
    df_filtered = df_stones[
        (df_stones["Форма"] == form) &
        (df_stones["Название"] == stone_type)
    ].copy()
    df_filtered["delta"] = ((df_filtered["Длина"] - length)**2 + (df_filtered["Ширина"] - width)**2)**0.5
    df_nearest = df_filtered[df_filtered["delta"] <= 3.0].sort_values(by="delta")
    if not df_nearest.empty:
        best = df_nearest.iloc[0]
        delta = best["delta"]
        if delta < 1.0:
            corrected_weight = best["Вес сброса"]
        else:
            correction = min(0.1 * delta, 0.15)
            if length > best["Длина"] or width > best["Ширина"]:
                corrected_weight = round(best["Вес сброса"] * (1 + correction), 2)
            else:
                corrected_weight = round(best["Вес сброса"] * (1 - correction), 2)
        return best["Длина"], best["Ширина"], best["Высота"], corrected_weight
    return None

def identify_stone_with_vision(image_url):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты эксперт-геммолог. Игнорируй руки, кожу, кольца. Определи:\n- Вид\n- Альтернатива\n- Форму (овал, кабошон, маркиз и т.д.)\n\nФормат:\nВид: [Название]\nАльтернатива: [Вариант]\nФорма: [Форма]"},
                {"role": "user", "content": [
                    {"type": "text", "text": "Что это за камень? Только камень на фото. Дай вид, альтернативу и форму."},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("❌ Vision ошибка:", e)
        return None

@app.route("/", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]

        if "photo" in message:
            file_id = message["photo"][-1]["file_id"]
            caption = message.get("caption", "")
            length, width = extract_dimensions(caption)
            file_url = get_file_url(file_id)

            vision_result = identify_stone_with_vision(file_url)
            form, stone_type = None, None

            manual_type = extract_manual_type(caption)
            if manual_type:
                stone_type = manual_type.strip().capitalize()
            elif vision_result:
                form_match = re.search(r"Форма[:\s]+(.+)", vision_result, re.IGNORECASE)
                if form_match:
                    form = form_match.group(1).strip().lower()
                type_match = re.search(r"Вид[:\s]+(.+)", vision_result, re.IGNORECASE)
                if type_match:
                    stone_type = type_match.group(1).strip().capitalize().split("(")[0]
                    if stone_type.lower() == "перидот":
                        stone_type = "Хризолит"

            response_text = ""
            density = ALL_DENSITIES.get(stone_type)

            if length and width and form and stone_type and density:
                if form in ["сфера", "шар"]:
                    radius = length / 2
                    volume = (4/3) * pi * (radius ** 3)
                    weight = round(volume * density / 1000, 2)
                    response_text += f"⚫️ Сфера\n📏 Диаметр: {length} мм\n⚖️ Вес: ~{weight} г\n"
                else:
                    result = find_closest_stone(length, width, form, stone_type)
                    if result:
                        best_length, best_width, best_height, corrected_weight = result
                        response_text += (
                            f"📏 Размер: {best_length} × {best_width} × {best_height} мм\n"
                            f"⚖️ Вес: ~{corrected_weight} г\n"
                            f"📐 Форма: {form}\n"
                        )
                    else:
                        avg_h = (length + width) / 4
                        volume = (pi * length * width * avg_h) / 6
                        weight = round(volume * density / 1000, 2)
                        response_text += (
                            f"📐 Форма: {form}\n"
                            f"📏 Размер: {length} × {width} × {round(avg_h, 2)} мм\n"
                            f"⚖️ Расчётный вес: ~{weight} г по плотности {density}\n"
                        )

            if vision_result:
                response_text += f"\n🧠 Vision:\n{vision_result}"
            else:
                response_text += "🤖 Не удалось распознать камень."

            send_message(chat_id, response_text)
        else:
            send_message(chat_id, "📷 Пришли фото камня с размерами в подписи.")

    return "ok"

@app.route("/", methods=["GET"])
def index():
    return "✅ Бот работает", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)