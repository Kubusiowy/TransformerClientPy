from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request


JUSTSEND_API_URL = "https://justsend.pl/api/rest/v2/message/send"
VALID_BULK_VARIANTS = {"PRO", "ECO", "FULL", "ECO_RESP", "PRO_RESP", "VOICE"}


class SmsSendError(Exception):
    pass


class JustSendSmsClient:
    def __init__(self) -> None:
        self.logger = logging.getLogger("transformer_client.sms")

    def send_message(
        self,
        api_key: str,
        sender: str,
        phone_numbers: list[str],
        message: str,
        bulk_variant: str = "PRO",
    ) -> str:
        api_key = api_key.strip()
        if not api_key:
            raise SmsSendError("Brak klucza API SMS.")
        if not message.strip():
            raise SmsSendError("Wiadomosc SMS jest pusta.")

        normalized_numbers = self._normalize_numbers(phone_numbers)
        if not normalized_numbers:
            raise SmsSendError("Brak poprawnych numerow telefonu.")

        normalized_sender = self._normalize_sender(sender)
        variant = bulk_variant.strip().upper() or "PRO"
        if variant not in VALID_BULK_VARIANTS:
            variant = "PRO"

        sent_count = 0
        errors: list[str] = []
        for phone_number in normalized_numbers:
            payload = {
                "message": message,
                "from": normalized_sender,
                "to": phone_number,
                "bulkVariant": variant,
                "doubleEncode": True,
            }
            try:
                self._post(api_key, payload)
                sent_count += 1
                self.logger.info("SMS sent phone=%s sender=%s", phone_number, normalized_sender)
            except SmsSendError as exc:
                error_message = f"{phone_number}: {exc}"
                errors.append(error_message)
                self.logger.error("SMS send failed %s", error_message)

        if sent_count == 0:
            raise SmsSendError("; ".join(errors) if errors else "Nie udalo sie wyslac SMS.")

        if errors:
            return f"Wyslano do {sent_count} numerow, bledy: {'; '.join(errors[:2])}"
        return f"Wyslano do {sent_count} numerow."

    def _post(self, api_key: str, payload: dict) -> None:
        request = urllib.request.Request(
            JUSTSEND_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "App-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "TransformerClientPy/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
                body = json.loads(raw_body) if raw_body else {}
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(response_body) if response_body else {}
            except json.JSONDecodeError:
                body = {}
            message = body.get("message") or response_body or f"HTTP {exc.code}"
            raise SmsSendError(f"HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise SmsSendError(f"Blad polaczenia: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise SmsSendError("Nieprawidlowa odpowiedz JSON z API SMS.") from exc

        if body.get("responseCode") != "OK" or int(body.get("errorId", 0)) != 0:
            message = body.get("message") or "Nieznany blad API SMS."
            raise SmsSendError(message)

    @staticmethod
    def _normalize_sender(sender: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9]", "", sender or "")
        return (normalized or "Transformer")[:11]

    @staticmethod
    def _normalize_numbers(phone_numbers: list[str]) -> list[str]:
        normalized_numbers: list[str] = []
        for phone_number in phone_numbers:
            digits = re.sub(r"[^0-9]", "", phone_number or "")
            if not digits:
                continue
            if len(digits) == 9:
                digits = "48" + digits
            if len(digits) == 11 and digits.startswith("48"):
                normalized_numbers.append(digits)
        return normalized_numbers
