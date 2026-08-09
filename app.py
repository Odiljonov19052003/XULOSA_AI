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
import secrets
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session, redirect
from dotenv import load_dotenv
import anthropic

load_dotenv()

APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "data.json"
STATIC_DIR = APP_DIR / "static"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-5")
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "")  # bo'sh bo'lsa - parol so'ralmaydi

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
_lock = threading.Lock()  # bir vaqtda ikkita yozuv to'qnashmasligi uchun

LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Kirish</title>
<style>
  body{background:#0E1013;color:#EDEFF3;font-family:-apple-system,sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
  .box{background:#171A20;border:1px solid #2A2F3A;border-radius:16px;padding:32px;width:280px;}
  h1{font-size:18px;margin:0 0 18px;}
  input{width:100%;padding:10px;border-radius:8px;border:1px solid #2A2F3A;
        background:#1E222A;color:#EDEFF3;margin-bottom:12px;box-sizing:border-box;font-size:14px;}
  button{width:100%;padding:10px;border-radius:8px;border:none;font-weight:600;
         background:linear-gradient(135deg,#5B8DEF,#3FD6A8);color:#0E1013;cursor:pointer;font-size:14px;}
  .err{color:#FF6B5F;font-size:13px;margin:-6px 0 12px;}
</style></head>
<body>
  <form class="box" method="POST" action="/login">
    <h1>Faoliyat Paneli</h1>
    {error_html}
    <input type="password" name="password" placeholder="Parol" autofocus>
    <button type="submit">Kirish</button>
  </form>
</body></html>"""


@app.before_request
def require_login():
    if not SITE_PASSWORD:
        return  # parol sozlanmagan - himoyasiz ishlaydi
    if request.path == "/login":
        return
    if not session.get("auth"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Avtorizatsiya talab qilinadi"}), 401
        return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    error_html = ""
    if request.method == "POST":
        if request.form.get("password") == SITE_PASSWORD:
            session["auth"] = True
            session.permanent = True
            return redirect("/")
        error_html = '<p class="err">Parol noto\'g\'ri</p>'
    return LOGIN_HTML.replace("{error_html}", error_html)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


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
