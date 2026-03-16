import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()



def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set")
    return value


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=_require_env("OPENAI_API_KEY"),
        base_url=_require_env("OPENAI_BASE_URL"),
    )


async def answer_user_message(
    system: str,
    user_query: str,
    model: str = "gpt-4o-mini",
    temp: float = 0.2,
) -> str:
    client = _get_client()
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_query},
        ],
        temperature=temp,
    )
    return response.choices[0].message.content or "Не удалось сформировать ответ"


async def summarize_dialog_history(
    previous_summary: str,
    recent_dialog: str,
    model: str = "gpt-4o-mini",
) -> str:
    client = _get_client()
    messages = [
        {
            "role": "system",
            "content": (
                "Ты аккуратный суммаризатор диалога для memory-компрессии. "
                "Сделай краткую, полезную сводку на русском: цели пользователя, "
                "важные факты, триггеры, прогресс, договоренности, последние проблемы. "
                "Без воды, без выдумок, до 1200 символов."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Текущая сводка:\n{previous_summary or '(пусто)'}\n\n"
                f"Новые сообщения:\n{recent_dialog}"
            ),
        },
    ]

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content or previous_summary


