import unittest
from types import SimpleNamespace
from unittest.mock import patch

from max_reviews_bot import app


class AppLogicTests(unittest.TestCase):
    def test_extract_message_meta(self):
        update = {
            "message": {
                "recipient": {"chat_id": 42, "chat_type": "dialog", "user_id": 777},
                "sender": {"user_id": 123},
                "body": {"mid": "m1", "seq": 5, "text": "Привет", "attachments": []},
            }
        }
        meta = app.extract_message_meta(update)
        self.assertEqual(meta["chat_id"], 42)
        self.assertEqual(meta["sender"], 123)
        self.assertEqual(meta["text"], "Привет")

    def test_extract_first_attachment_info(self):
        update = {
            "message": {
                "recipient": {"chat_id": 42, "chat_type": "dialog", "user_id": 777},
                "sender": {"user_id": 123},
                "body": {
                    "attachments": [
                        {"type": "image", "payload": {"url": "https://x/y.jpg"}}
                    ]
                },
            }
        }
        att = app.extract_first_attachment_info(update)
        self.assertEqual(att["type"], "image")
        self.assertEqual(att["url"], "https://x/y.jpg")

    def test_is_start_message(self):
        self.assertTrue(app.is_start_message({"text": "/start"}))
        self.assertTrue(app.is_start_message({"text": "start"}))
        self.assertFalse(app.is_start_message({"text": "hello"}))

    def test_is_audio_attachment_by_type(self):
        self.assertTrue(app.is_audio_attachment("voice", None))
        self.assertTrue(app.is_audio_attachment("audio", None))
        self.assertFalse(app.is_audio_attachment("image", None))

    def test_is_audio_attachment_by_url(self):
        self.assertTrue(app.is_audio_attachment(None, "https://cdn/voice.ogg"))
        self.assertTrue(app.is_audio_attachment(None, "https://cdn/file.MP3"))
        self.assertFalse(app.is_audio_attachment(None, "https://cdn/file.jpg"))

    def test_transcribe_audio_file_uses_ru(self):
        captured = {}

        class MockModel:
            def transcribe(self, file_path, language, vad_filter):
                captured["file_path"] = file_path
                captured["language"] = language
                captured["vad_filter"] = vad_filter
                return [SimpleNamespace(text="привет"), SimpleNamespace(text="мир")], None

        with patch("max_reviews_bot.app.get_whisper_model", return_value=MockModel()):
            text = app.transcribe_audio_file("/tmp/a.ogg")

        self.assertEqual(text, "привет мир")
        self.assertEqual(captured["language"], "ru")
        self.assertTrue(captured["vad_filter"])


if __name__ == "__main__":
    unittest.main()
