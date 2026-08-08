"""
Moliya Daftari — backend server.

Bu server:
1. Saytning o'zini (static/index.html) ko'rsatadi
2. Yuklangan moliyaviy yozuvlarni serverda (data.json faylida) saqlaydi,
   shunda barcha rahbarlar bir xil ma'lumotni ko'radi
3. AI xulosa so'rovini Anthropic API'ga API kalitni YASHIRIN holda yuboradi
   (kalit hech qachon brauzerga, foydalanuvchiga ko'rinmaydi)
"""
import os
import json
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
import anthropic

load_dotenv()

APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "data.json"
STATIC_DIR = APP_DIR / "static"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-5")

app = Flask(__name__, static_folder=None)
_lock = threading.Lock()  # bir vaqtda ikkita yozuv to'qnashmasligi uchun


def _load_entries():
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_entries(entries):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def _row_key(r):
    return (r.get("Sana"), r.get("Turi"), r.get("Kategoriya"), r.get("Bolim"), r.get("Summa"))


# ---------- Sayt fayllarini ko'rsatish ----------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# ---------- Ma'lumotlar API'si ----------

@app.route("/api/entries", methods=["GET"])
def get_entries():
    return jsonify({"entries": _load_entries()})


@app.route("/api/entries", methods=["POST"])
def add_entries():
    payload = request.get_json(force=True, silent=True) or {}
    new_rows = payload.get("entries", [])
    if not isinstance(new_rows, list):
        return jsonify({"error": "entries ro'yxat (list) bo'lishi kerak"}), 400

    with _lock:
        existing = _load_entries()
        seen = {_row_key(r) for r in existing}
        added = 0
        for r in new_rows:
            key = _row_key(r)
            if key not in seen:
                existing.append(r)
                seen.add(key)
                added += 1
        existing.sort(key=lambda r: r.get("Sana", ""))
        _save_entries(existing)

    return jsonify({"entries": existing, "added": added})


@app.route("/api/entries", methods=["DELETE"])
def clear_entries():
    with _lock:
        _save_entries([])
    return jsonify({"ok": True})


# ---------- AI xulosa ----------

@app.route("/api/xulosa", methods=["POST"])
def xulosa():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Serverda ANTHROPIC_API_KEY sozlanmagan (.env faylni tekshiring)"}), 500

    payload = request.get_json(force=True, silent=True) or {}
    context = payload.get("context", "").strip()
    if not context:
        return jsonify({"error": "context bo'sh bo'lmasligi kerak"}), 400

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=AI_MODEL,
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": (
                    "Sen kompaniya rahbari uchun moliyaviy tahlilchisan. Quyidagi ma'lumotlar "
                    "asosida O'ZBEK TILIDA, qisqa (5-7 gap), aniq va amaliy xulosa yoz. Faqat "
                    "berilgan raqamlardan foydalan, hech narsa o'ylab topma. Trend, xavotirli "
                    f"joy va bitta amaliy tavsiya ber:\n\n{context}"
                ),
            }],
        )
        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ).strip()
        return jsonify({"xulosa": text or "AI javob qaytarmadi."})
    except anthropic.APIError as e:
        return jsonify({"error": f"Anthropic API xatosi: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
