"""
Simple Telegram notifier using the Bot API (no extra dependencies).
"""

import requests
import config


def send_telegram_message(text, parse_mode="Markdown"):
    if (not config.TELEGRAM_BOT_TOKEN or "PUT_YOUR" in config.TELEGRAM_BOT_TOKEN
            or not config.TELEGRAM_CHAT_ID or "PUT_YOUR" in config.TELEGRAM_CHAT_ID):
        print("[telegram] Skipped (token/chat_id not configured).")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"[telegram] Error {resp.status_code}: {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"[telegram] Exception: {e}")
        return False


def format_signal_message(signal):
    pair = signal["pair"].replace("_", "/")
    checks = signal["checks"]

    check_lines = []
    for name, passed in checks.items():
        icon = "✅" if passed else "❌"
        check_lines.append(f"{icon} {name}")

    msg = (
        f"🟢 *LONG SIGNAL* — `{pair}`\n"
        f"Confluence Score: *{signal['score']}/{signal['max_score']}*\n\n"
        f"*Entry:* `{signal['entry']:.6g}`\n"
        f"*Stop Loss:* `{signal['stop_loss']:.6g}`\n"
        f"*TP1:* `{signal['tp1']:.6g}` (R:R {signal['rr1']})\n"
        f"*TP2:* `{signal['tp2']:.6g}` (R:R {signal['rr2']})\n"
        f"*TP3:* `{signal['tp3']:.6g}` (R:R {signal['rr3']})\n\n"
        f"*4h Bias:* {signal['htf']['bias'].upper()}\n"
        f"*15m RSI:* {signal['ltf']['rsi']:.1f}\n\n"
        f"*Checklist:*\n" + "\n".join(check_lines)
    )
    return msg
