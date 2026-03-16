# Neurodietolog Bot

Telegram-бот по похудению с:
- текстовыми ответами,
- STT (распознавание речи),
- TTS (голосовые ответы),
- напоминаниями раз в 2 часа (тихий режим с 01:00 до 08:00),
- хранением памяти в SQLite и авто-суммаризацией.

## Переменные окружения

### Обязательные

```env
TELEGRAM_TOKEN=...
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.vsellm.ru/v1
WEBHOOK_BASE_URL=https://neurodietolog.containerapps.ru
```

### Рекомендуемые для webhook

```env
WEBHOOK_PATH=/webhook
WEBHOOK_SECRET=long_random_secret
WEBAPP_HOST=0.0.0.0
WEBAPP_PORT=8080
```

### STT/TTS и локальные файлы (для Container App)

```env
STT_MODEL=tiny
STT_CACHE_DIR=/tmp/.cache/faster-whisper
PIPER_DIR=/tmp/voices
PIPER_LENGTH_SCALE=1.22
PIPER_SENTENCE_SILENCE_MS=220
BOT_DB_PATH=/tmp/bot_memory.db
SUBSCRIBERS_FILE=/tmp/subscribed_users.json
LOG_FILE=
```

Примечание:
- `LOG_FILE` лучше оставить пустым в контейнере, чтобы логи шли в stdout/stderr.
- `ffmpeg` ставится в образе через `Dockerfile`.

## Локальный запуск (PowerShell)

```powershell
cd C:\Users\Игорь\projects\Bot_diet
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python bot.py
```

## Сборка и push образа (cloud.ru)

```bash
docker login neurodietolog.cr.cloud.ru -u <USER> -p <PASSWORD>
docker build . --platform linux/amd64 -t neurodietolog.cr.cloud.ru/neurodietolog:latest
docker push neurodietolog.cr.cloud.ru/neurodietolog:latest
```

## Установка webhook в Telegram API

```text
https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook?url=https://neurodietolog.containerapps.ru/webhook&drop_pending_updates=true
```

Проверка webhook:

```text
https://api.telegram.org/bot<TELEGRAM_TOKEN>/getWebhookInfo
```
