import os
import openai

# ✅ Получаем ключ из переменной окружения
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# Тестовая ссылка на фото камня (замени на своё фото по ссылке, если надо)
image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/Ruby_gem.JPG/1200px-Ruby_gem.JPG"

try:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "Ты эксперт-геммолог. Игнорируй фон и пальцы. Дай: Вид: [Название] Альтернатива: [Вариант] Форма: [Форма]"
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Что за камень на фото?"},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ],
        max_tokens=150
    )
    print("🧠 Ответ Vision:\n", response.choices[0].message.content.strip())

except openai.OpenAIError as e:
    print("❌ Ошибка Vision:\n", e)


