import os
import openai

# ✅ Читаем ключ из переменной окружения
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/Ruby_gem.JPG/1200px-Ruby_gem.JPG"

try:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "Ты эксперт-геммолог. Игнорируй фон и пальцы. Дай:\nВид: [Название]\nАльтернатива: [Вариант]\nФорма: [Форма]"
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
    print("🧠 Ответ Vision:")
    print(response.choices[0].message.content.strip())
except Exception as e:
    print("❌ Ошибка Vision:")
    print(e)

