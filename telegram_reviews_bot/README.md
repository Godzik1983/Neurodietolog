# Telegram Reviews Bot

Ветка для адаптации логики `max_reviews_bot` под Telegram.

## Структура
- `bot.py` - Telegram транспорт (aiogram polling)
- `core_logic.py` - копия текущей бизнес-логики из Max-бота как база для переноса

## Запуск
1. Скопируйте env:
```bash
cp telegram_reviews_bot/.env.example telegram_reviews_bot/.env
```
2. Заполните `TELEGRAM_TOKEN` и OpenAI переменные.
3. Запуск:
```bash
docker compose -f docker-compose.telegram.yml up -d --build
```
