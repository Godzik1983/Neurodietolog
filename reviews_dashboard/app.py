import json
import os
from datetime import datetime

import pandas as pd
import psycopg2
import requests
import streamlit as st


st.set_page_config(page_title="Reviews Dashboard", layout="wide")
st.title("Dashboard: Жалобы и статусы диалогов")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://botuser:botpass123@host.docker.internal:5432/botdb",
).strip()
MAX_BOT_ID = os.getenv("MAX_BOT_ID", "").strip()
TELEGRAM_BOT_ID = os.getenv("TELEGRAM_BOT_ID", "").strip()
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "").strip()
MAX_BASE_URL = os.getenv("MAX_BASE_URL", "https://platform-api.max.ru").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

if not DATABASE_URL:
    st.error("DATABASE_URL не задан")
    st.stop()


@st.cache_data(ttl=30)
def load_chats() -> pd.DataFrame:
    conn = psycopg2.connect(DATABASE_URL)
    query = """
    SELECT
        c.chat_id,
        c.platform,
        c.sender,
        c.bot,
        c.send_disabled,
        c.send_disabled_reason,
        c.finish,
        c.result,
        c.tone_of_voice,
        c.complaint_raw_text,
        c.first_seen_at,
        c.last_seen_at,
        (
            SELECT m.text
            FROM messages m
            WHERE m.chat_id = c.chat_id
            ORDER BY m.id DESC
            LIMIT 1
        ) AS last_message_text,
        (
            SELECT m.raw_json
            FROM messages m
            WHERE m.chat_id = c.chat_id
            ORDER BY m.id DESC
            LIMIT 1
        ) AS last_raw_json
    FROM chats c
    ORDER BY c.last_seen_at DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


@st.cache_data(ttl=30)
def load_messages(chat_id: str) -> pd.DataFrame:
    conn = psycopg2.connect(DATABASE_URL)
    query = """
    SELECT id, direction, text, attachment_type, created_at
    FROM messages
    WHERE chat_id = %s
    ORDER BY id ASC
    """
    df = pd.read_sql_query(query, conn, params=(chat_id,))
    conn.close()
    return df


def set_manual_mode(chat_id: str, reason: str = "dashboard_manual_reply") -> None:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chats
                    SET send_disabled = 1,
                        send_disabled_reason = %s,
                        last_seen_at = %s
                    WHERE chat_id = %s
                    """,
                    (reason, datetime.now().isoformat(timespec="seconds"), str(chat_id)),
                )
    finally:
        conn.close()


def save_outgoing_message(
    platform: str,
    chat_id: str,
    sender_user_id: str,
    recipient_user_id: str,
    message_id: str,
    text: str,
    raw_json: str,
) -> None:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO messages (
                        direction,
                        platform,
                        chat_id,
                        sender_user_id,
                        recipient_user_id,
                        message_id,
                        seq,
                        text,
                        attachment_type,
                        attachment_url,
                        file_path,
                        raw_json,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, NULL, NULL, NULL, %s, %s)
                    """,
                    (
                        "outgoing",
                        platform,
                        str(chat_id),
                        str(sender_user_id) if sender_user_id else None,
                        str(recipient_user_id) if recipient_user_id else None,
                        str(message_id) if message_id else None,
                        text,
                        raw_json,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
    finally:
        conn.close()


def parse_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def detect_source(bot_value, raw_json_value) -> str:
    bot_str = "" if pd.isna(bot_value) else str(bot_value)
    raw = "" if pd.isna(raw_json_value) else str(raw_json_value)

    if MAX_BOT_ID and bot_str == MAX_BOT_ID:
        return "MAX"
    if TELEGRAM_BOT_ID and bot_str == TELEGRAM_BOT_ID:
        return "Telegram"
    if "platform-api.max.ru" in raw or '"chat_type": "dialog"' in raw:
        return "MAX"
    if '"update_id"' in raw or '"from": {' in raw or '"entities":' in raw:
        return "Telegram"
    return "Unknown"


def send_telegram_message(chat_id: str, text: str) -> dict:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")
    return payload


def send_max_message(chat_id: str, text: str) -> dict:
    if not MAX_BOT_TOKEN:
        raise RuntimeError("MAX_BOT_TOKEN is not set")
    response = requests.post(
        f"{MAX_BASE_URL}/messages",
        headers={"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"},
        params={"chat_id": chat_id},
        json={"text": text, "notify": True},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_message_to_chat(platform: str, chat_id: str, text: str) -> dict:
    platform_normalized = (platform or "").strip().lower()
    if platform_normalized == "telegram":
        return send_telegram_message(chat_id, text)
    if platform_normalized == "max":
        return send_max_message(chat_id, text)
    raise RuntimeError(f"Unsupported platform: {platform}")


def extract_message_id(platform: str, payload: dict) -> str:
    platform_normalized = (platform or "").strip().lower()
    if platform_normalized == "telegram":
        result = payload.get("result", {})
        return str(result.get("message_id") or "")
    if platform_normalized == "max":
        return str(
            payload.get("message_id")
            or payload.get("id")
            or payload.get("body", {}).get("mid")
            or ""
        )
    return ""


df = load_chats()
if df.empty:
    st.warning("В таблице chats пока нет данных.")
    st.stop()

df["first_seen_at_dt"] = parse_dt(df["first_seen_at"])
df["last_seen_at_dt"] = parse_dt(df["last_seen_at"])
df["complaint_text"] = df["complaint_raw_text"].fillna("").str.strip()
df["source"] = df["platform"].fillna("").replace({"max": "MAX", "telegram": "Telegram"})
df.loc[df["source"] == "", "source"] = df.apply(
    lambda row: detect_source(row.get("bot"), row.get("last_raw_json")),
    axis=1,
)

st.subheader("Фильтры")
col1, col2, col3, col4, col5 = st.columns(5)

min_date = df["last_seen_at_dt"].min().date() if df["last_seen_at_dt"].notna().any() else datetime.now().date()
max_date = df["last_seen_at_dt"].max().date() if df["last_seen_at_dt"].notna().any() else datetime.now().date()

date_from = col1.date_input("Дата от", value=min_date)
date_to = col2.date_input("Дата до", value=max_date)
finish_options = sorted(df["finish"].dropna().astype(int).unique().tolist())
selected_finish = col3.multiselect("Finish", options=finish_options, default=finish_options)
selected_results = col4.multiselect(
    "Result",
    options=sorted(df["result"].dropna().unique().tolist()),
    default=sorted(df["result"].dropna().unique().tolist()),
)
selected_sources = col5.multiselect(
    "Источник",
    options=sorted(df["source"].dropna().unique().tolist()),
    default=sorted(df["source"].dropna().unique().tolist()),
)

col6, col7 = st.columns(2)
chat_id_filter = col6.text_input("chat_id содержит")
complaint_filter = col7.text_input("Текст жалобы содержит")

filtered = df.copy()
filtered = filtered[
    (filtered["last_seen_at_dt"].dt.date >= date_from)
    & (filtered["last_seen_at_dt"].dt.date <= date_to)
]
if selected_finish:
    filtered = filtered[filtered["finish"].astype(int).isin(selected_finish)]
if selected_results:
    filtered = filtered[filtered["result"].isin(selected_results)]
if selected_sources:
    filtered = filtered[filtered["source"].isin(selected_sources)]
if chat_id_filter.strip():
    filtered = filtered[filtered["chat_id"].astype(str).str.contains(chat_id_filter.strip(), na=False)]
if complaint_filter.strip():
    filtered = filtered[
        filtered["complaint_text"].str.contains(complaint_filter.strip(), case=False, na=False)
    ]

total_chats = len(filtered)
finished_chats = int((filtered["finish"] == 1).sum()) if total_chats else 0
negative_chats = int((filtered["complaint_text"].str.len() > 0).sum()) if total_chats else 0

st.subheader("Сводка")
s1, s2, s3 = st.columns(3)
s1.metric("Чатов", total_chats)
s2.metric("Завершено", finished_chats)
s3.metric("С жалобой", negative_chats)

st.subheader("Список жалоб")
table_df = filtered[
    [
        "source",
        "chat_id",
        "sender",
        "bot",
        "last_seen_at",
        "finish",
        "result",
        "tone_of_voice",
        "complaint_text",
        "last_message_text",
    ]
].rename(
    columns={
        "source": "Источник",
        "chat_id": "Chat ID",
        "sender": "Клиент ID",
        "bot": "Бот ID",
        "last_seen_at": "Когда",
        "finish": "Finish",
        "result": "Result",
        "tone_of_voice": "Tone",
        "complaint_text": "Что не понравилось",
        "last_message_text": "Последнее сообщение",
    }
)
st.dataframe(table_df, use_container_width=True)

csv_data = table_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Выгрузить CSV",
    data=csv_data,
    file_name="reviews_dashboard_export.csv",
    mime="text/csv",
)

st.subheader("Детали чата")
chat_ids = filtered["chat_id"].astype(str).tolist()
if chat_ids:
    if st.button("Обновить чат"):
        load_chats.clear()
        load_messages.clear()
        st.rerun()

    selected_chat = st.selectbox("Выберите chat_id", options=chat_ids, index=0)
    selected_chat_row = filtered[filtered["chat_id"].astype(str) == str(selected_chat)].iloc[0]
    if int(selected_chat_row.get("send_disabled") or 0) == 1:
        reason = selected_chat_row.get("send_disabled_reason") or "manual mode"
        st.info(f"Автоответы бота отключены. Режим ручного общения: {reason}")
    msg_df = load_messages(selected_chat).rename(
        columns={
            "id": "ID",
            "direction": "Направление",
            "text": "Текст",
            "attachment_type": "Тип вложения",
            "created_at": "Когда",
        }
    )
    st.dataframe(msg_df, use_container_width=True)

    st.subheader("Новые сообщения гостя")
    incoming_df = msg_df[msg_df["Направление"] == "incoming"]
    if incoming_df.empty:
        st.caption("Новых входящих сообщений пока нет.")
    else:
        st.dataframe(incoming_df.tail(10), use_container_width=True)

    st.subheader("Написать гостю")
    st.caption("Сообщение уйдет в тот же чат от имени бота.")
    reply_key = f"reply_text_{selected_chat}"
    if reply_key not in st.session_state:
        st.session_state[reply_key] = (
            "Здравствуйте! Сожалеем о ситуации. Подскажите, пожалуйста, чем мы можем помочь?"
        )

    with st.form(key=f"reply_form_{selected_chat}", clear_on_submit=False):
        st.text_area("Текст сообщения", key=reply_key, height=120)
        submitted = st.form_submit_button("Отправить гостю")
        if submitted:
            reply_text = (st.session_state.get(reply_key) or "").strip()
            if not reply_text:
                st.error("Введите текст сообщения.")
            else:
                try:
                    payload = send_message_to_chat(
                        str(selected_chat_row["platform"]),
                        str(selected_chat),
                        reply_text,
                    )
                    set_manual_mode(str(selected_chat))
                    save_outgoing_message(
                        platform=str(selected_chat_row["platform"]),
                        chat_id=str(selected_chat),
                        sender_user_id=str(selected_chat_row.get("bot") or ""),
                        recipient_user_id=str(selected_chat_row.get("sender") or ""),
                        message_id=extract_message_id(str(selected_chat_row["platform"]), payload),
                        text=reply_text,
                        raw_json=json.dumps(payload, ensure_ascii=False),
                    )
                    load_chats.clear()
                    load_messages.clear()
                    st.success("Сообщение отправлено гостю. Автоответы бота для этого чата отключены.")
                except Exception as exc:
                    st.error(f"Не удалось отправить сообщение: {exc}")
else:
    st.info("Нет чатов по текущему фильтру.")
