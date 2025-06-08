import openai

client = openai.OpenAI(
    api_key="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"
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
        max_tokens=200
    )

    print("✅ Ответ от Vision:\n")
    print(response.choices[0].message.content)

except Exception as e:
    print("❌ Ошибка Vision:\n", e)
