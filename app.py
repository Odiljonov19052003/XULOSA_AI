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


def _load_data():
    if not DATA_FILE.exists():
        return {"fakturalar": [], "tolovlar": [], "xarajatlar": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return {
                "fakturalar": d.get("fakturalar", []),
                "tolovlar": d.get("tolovlar", []),
                "xarajatlar": d.get("xarajatlar", []),
            }
    except (json.JSONDecodeError, OSError):
        return {"fakturalar": [], "tolovlar": [], "xarajatlar": []}


def _save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _faktura_key(r):
    return (r.get("Sana"), r.get("Viloyat"), r.get("Apteka"), r.get("Mahsulot"), r.get("Soni"), r.get("Summa"))


def _tolov_key(r):
    return (r.get("Sana"), r.get("Viloyat"), r.get("Apteka"), r.get("Tolov_summasi"))


def _xarajat_key(r):
    return (r.get("Sana"), r.get("Viloyat"), r.get("Kategoriya"), r.get("Summa"))


def _merge(existing_list, new_list, key_fn):
    seen = {key_fn(r) for r in existing_list}
    added = 0
    for r in new_list:
        k = key_fn(r)
        if k not in seen:
            existing_list.append(r)
            seen.add(k)
            added += 1
    existing_list.sort(key=lambda r: r.get("Sana", ""))
    return added


# ---------- Sayt fayllarini ko'rsatish ----------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# ---------- Ma'lumotlar API'si ----------

@app.route("/api/data", methods=["GET"])
def get_data():
    return jsonify(_load_data())


@app.route("/api/data", methods=["POST"])
def add_data():
    payload = request.get_json(force=True, silent=True) or {}
    new_fakturalar = payload.get("fakturalar", [])
    new_tolovlar = payload.get("tolovlar", [])
    new_xarajatlar = payload.get("xarajatlar", [])

    with _lock:
        data = _load_data()
        added = {
            "fakturalar": _merge(data["fakturalar"], new_fakturalar, _faktura_key),
            "tolovlar": _merge(data["tolovlar"], new_tolovlar, _tolov_key),
            "xarajatlar": _merge(data["xarajatlar"], new_xarajatlar, _xarajat_key),
        }
        _save_data(data)

    return jsonify({**data, "added": added})


@app.route("/api/data", methods=["DELETE"])
def clear_data():
    with _lock:
        _save_data({"fakturalar": [], "tolovlar": [], "xarajatlar": []})
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
