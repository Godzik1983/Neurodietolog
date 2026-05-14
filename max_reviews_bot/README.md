# Max Reviews Bot (from prototype notebook)

Этот сервис переносит логику из `_Prototip_v2_0.ipynb` в docker-ready бот, отдельно от текущего `bot.py`.

## Что внутри
- Polling `https://platform-api.max.ru/updates`
- Хранение диалогов в SQLite (`/data/max_dialogs.db`)
- Классификация состояния/тона диалога через OpenAI
- RAG-ответы через локальный FAISS индекс
- Проверка скриншота отзыва через vision-модель OpenAI
- Распознавание входящих голосовых через локальный `faster-whisper` (`tiny`, язык `ru`)
- Ответы бота всегда только текстом (без TTS)

## Подготовка
1. Скопируйте переменные окружения:
```bash
cp max_reviews_bot/.env.example max_reviews_bot/.env
```
2. Заполните минимум:
- `OPENAI_API_KEY`
- `MAX_BOT_TOKEN`
- Для безопасного теста с телефона можно включить `TEST_MODE=true` в `max_reviews_bot/.env`

3. Проверьте FAISS индекс в `max_reviews_bot/faiss_index/`:
- `index.faiss`
- `index.pkl`

## Запуск
```bash
docker compose -f docker-compose.max.yml up -d --build
```

## Логи
```bash
docker compose -f docker-compose.max.yml logs -f max_reviews_bot
```

## Минимальные тесты
```bash
python -m unittest discover -s max_reviews_bot/tests -v
```

## Smoke-checklist
1. Отправить `/start` и проверить первое приветствие.
2. Отправить текст и проверить текстовый ответ бота.
3. Отправить голосовое на русском и проверить, что бот отвечает текстом (без TTS).
4. Отправить картинку не-скриншота отзыва и проверить запрос на повторный скрин.
5. Отправить сообщение вида "больше не пишите" и проверить завершение диалога.
