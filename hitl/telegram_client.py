"""
TradingGuard HITL - Lightweight Telegram Bot API Client
Supports HTTP/SOCKS proxies (v2rayN), long-polling, photo uploads, and inline keyboards.
"""

import os
import json
import requests
from typing import Optional, Dict, Any, List


class TelegramClient:
    def __init__(self, token: str, proxy: Optional[str] = None):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.session = requests.Session()
        if self.proxies:
            self.session.proxies.update(self.proxies)

    def _post(self, method: str, data: Optional[Dict[str, Any]] = None, files: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/{method}"
        try:
            resp = self.session.post(url, data=data, files=files, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[Telegram API] Error {resp.status_code}: {resp.text}")
                return None
        except Exception as e:
            print(f"[Telegram API] Request failed for {method}: {e}")
            return None

    def get_me(self) -> Optional[Dict[str, Any]]:
        """Verifies token validity and returns bot information."""
        return self._post("getMe")

    def get_updates(self, offset: Optional[int] = None, timeout: int = 25) -> List[Dict[str, Any]]:
        """Long-polling update retrieval."""
        data = {"timeout": timeout}
        if offset is not None:
            data["offset"] = offset
        res = self._post("getUpdates", data=data, timeout=timeout + 10)
        if res and res.get("ok"):
            return res.get("result", [])
        return []

    def _split_text(self, text: str, max_chunk_size: int = 3800) -> List[str]:
        """Splits long text into manageable chunks along line/paragraph boundaries, slicing oversized lines if necessary."""
        if len(text) <= max_chunk_size:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = []
        current_len = 0

        for line in lines:
            while len(line) > max_chunk_size:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0
                chunks.append(line[:max_chunk_size])
                line = line[max_chunk_size:]

            line_len = len(line) + 1
            if current_len + line_len > max_chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_len = line_len
            else:
                current_chunk.append(line)
                current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return [c for c in chunks if c.strip()]

    def send_message(self, chat_id: str | int, text: str, parse_mode: Optional[str] = "Markdown", reply_markup: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Sends a text message with automatic chunking for >3800 chars and plain-text fallback on parse errors."""
        chunks = self._split_text(text, max_chunk_size=3800)
        last_res = None

        for idx, chunk in enumerate(chunks):
            # Only attach reply_markup to the final chunk
            markup = reply_markup if (idx == len(chunks) - 1) else None
            data = {
                "chat_id": chat_id,
                "text": chunk
            }
            if parse_mode:
                data["parse_mode"] = parse_mode
            if markup:
                data["reply_markup"] = json.dumps(markup)

            res = self._post("sendMessage", data=data)
            if not res and parse_mode:
                # Automatic fallback to unparsed plain text
                fallback_data = {"chat_id": chat_id, "text": chunk}
                if markup:
                    fallback_data["reply_markup"] = json.dumps(markup)
                res = self._post("sendMessage", data=fallback_data)
            last_res = res

        return last_res

    def send_photo(self, chat_id: str | int, photo_path: str, caption: Optional[str] = None, parse_mode: str = "Markdown", reply_markup: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Uploads and sends a photo with optional caption and buttons."""
        if not os.path.exists(photo_path):
            print(f"[Telegram API] Photo not found: {photo_path}")
            return None

        data = {
            "chat_id": chat_id,
            "parse_mode": parse_mode
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        with open(photo_path, "rb") as f:
            files = {"photo": f}
            res = self._post("sendPhoto", data=data, files=files, timeout=30)
            if not res and parse_mode:
                data.pop("parse_mode", None)
                f.seek(0)
                res = self._post("sendPhoto", data=data, files=files, timeout=30)
            return res

    def send_media_group(self, chat_id: str | int, media_items: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """
        Uploads and sends a multi-photo album (media group).
        media_items is a list of dicts: [{'path': str, 'caption': str}, ...]
        """
        url = f"{self.base_url}/sendMediaGroup"
        media = []
        files = {}
        file_handles = []

        try:
            for i, item in enumerate(media_items):
                p = item.get("path", "")
                c = item.get("caption", "")
                if not os.path.exists(p):
                    continue
                field = f"photo_{i}"
                fh = open(p, "rb")
                file_handles.append(fh)
                files[field] = fh
                media.append({
                    "type": "photo",
                    "media": f"attach://{field}",
                    "caption": c,
                    "parse_mode": "Markdown"
                })

            if not media:
                return None

            data = {
                "chat_id": chat_id,
                "media": json.dumps(media)
            }
            resp = self.session.post(url, data=data, files=files, timeout=40)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[Telegram API] sendMediaGroup error {resp.status_code}: {resp.text}")
                return None
        except Exception as e:
            print(f"[Telegram API] sendMediaGroup failed: {e}")
            return None
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Acknowledges inline button clicks to dismiss loading spinners on Telegram UI."""
        data = {"callback_query_id": callback_query_id}
        if text:
            data["text"] = text
        return self._post("answerCallbackQuery", data=data)
