# Bot_diet

Telegram-бот по поддержке похудения с:
- текстовыми ответами,
- голосовым STT (локально),
- голосовым TTS (локально),
- напоминаниями каждые 2 часа (с 01:00 до 08:00 не пишет),
- сохранением истории в SQLite и авто-суммаризацией.

## Настройка `.env`

Минимально нужны:

```env
TELEGRAM_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.vsellm.ru/v1
```

## Локальный запуск (PowerShell)

```powershell
cd C:\Users\Игорь\projects\Bot_diet

# 1) Установить/обновить зависимости
venv\Scripts\python -m pip install -r requirements.txt

# 2) Запустить бота
venv\Scripts\python bot.py
```

## Запуск в фоне (PowerShell)

```powershell
cd C:\Users\Игорь\projects\Bot_diet
Start-Process -FilePath "venv\Scripts\python.exe" -ArgumentList "bot.py" -WorkingDirectory "."
```

## Проверить, что бот запущен

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*bot.py*" } |
  Select-Object ProcessId, CommandLine
```

## Остановить все экземпляры бота

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*bot.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

