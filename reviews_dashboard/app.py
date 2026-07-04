import os
from datetime import datetime

import pandas as pd
import psycopg2
import streamlit as st


st.set_page_config(page_title="Reviews Dashboard", layout="wide")
st.title("Dashboard: Жалобы и статусы диалогов")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://botuser:botpass123@host.docker.internal:5432/botdb",
).strip()
MAX_BOT_ID = os.getenv("MAX_BOT_ID", "").strip()
TELEGRAM_BOT_ID = os.getenv("TELEGRAM_BOT_ID", "").strip()

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
    selected_chat = st.selectbox("Выберите chat_id", options=chat_ids, index=0)
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
else:
    st.info("Нет чатов по текущему фильтру.")
