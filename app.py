"""
Xulosa AI — backend server.

Bu server:
1. Saytning o'zini (static/index.html) ko'rsatadi
2. Yuklangan HAR QANDAY Excel fayldan olingan (frontendda parse qilingan)
   umumiy (generic) jadval ma'lumotlarini serverda (data.json faylida)
   saqlaydi - "hisobot" sifatida, shunda hamma bir xil ma'lumotni ko'radi
3. AI xulosa so'rovini Anthropic API'ga API kalitni YASHIRIN holda yuboradi
   (kalit hech qachon brauzerga, foydalanuvchiga ko'rinmaydi)

Eski versiyada faqat qat'iy belgilangan 3 ta varaq (Fakturalar/Tolovlar/
Xarajatlar, aniq ustun nomlari bilan) qabul qilinardi. Endi fayl qanday
tuzilgan bo'lishidan qat'iy nazar (istalgan varaq nomlari, istalgan ustun
nomlari) ishlaydi - varaq/ustun turlarini frontend (static/index.html)
o'zi aniqlab, umumiy {nomi, ustunlar, qatorlar} ko'rinishida shu serverga
yuboradi.
"""
import os
import json
import time
import uuid
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

# Diskda / xotirada cheksiz o'sib ketmasligi uchun cheklovlar. Eski
# hisobotlar shu limitdan oshganda avtomatik (eng eskisidan) o'chiriladi.
MAX_HISOBOTLAR = 30
MAX_QATORLAR_PER_VARAQ = 20000

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB - juda katta so'rovlardan himoya
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
    <h1>Xulosa AI</h1>
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


# ---------- Ma'lumotlarni saqlash ----------

def _load_data():
    if not DATA_FILE.exists():
        return {"hisobotlar": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return {"hisobotlar": d.get("hisobotlar", [])}
    except (json.JSONDecodeError, OSError):
        return {"hisobotlar": []}


def _save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _hisobot_summary(h):
    """To'liq qator ma'lumotisiz, faqat ro'yxat uchun yengil ko'rinish."""
    return {
        "id": h["id"],
        "fayl_nomi": h["fayl_nomi"],
        "yuklangan_vaqt": h["yuklangan_vaqt"],
        "varaqlar": [
            {
                "nomi": v["nomi"],
                "ustunlar": v["ustunlar"],
                "qatorlar_soni": len(v.get("qatorlar", [])),
            }
            for v in h.get("varaqlar", [])
        ],
    }


# ---------- Sayt fayllarini ko'rsatish ----------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# ---------- Hisobotlar (har qanday Excel'dan olingan umumiy jadval) API'si ----------

@app.route("/api/hisobotlar", methods=["GET"])
def list_hisobotlar():
    """Faqat ro'yxat (yengil) - qatorlarsiz. Bittasini to'liq (qatorlari
    bilan) ko'rish uchun GET /api/hisobotlar/<id> ishlatiladi."""
    data = _load_data()
    return jsonify({"hisobotlar": [_hisobot_summary(h) for h in data["hisobotlar"]]})


@app.route("/api/hisobotlar/<hid>", methods=["GET"])
def get_hisobot(hid):
    data = _load_data()
    for h in data["hisobotlar"]:
        if h["id"] == hid:
            return jsonify(h)
    return jsonify({"error": "Hisobot topilmadi"}), 404


@app.route("/api/hisobotlar", methods=["POST"])
def add_hisobot():
    payload = request.get_json(force=True, silent=True) or {}
    fayl_nomi = str(payload.get("fayl_nomi", "") or "nomsiz_fayl.xlsx").strip()[:200]
    varaqlar_in = payload.get("varaqlar", [])
    if not isinstance(varaqlar_in, list) or not varaqlar_in:
        return jsonify({"error": "varaqlar bo'sh bo'lmasligi kerak"}), 400

    varaqlar = []
    for v in varaqlar_in:
        nomi = str(v.get("nomi", "") or "Varaq")[:120]
        ustunlar = v.get("ustunlar", [])
        qatorlar = v.get("qatorlar", [])
        if not isinstance(qatorlar, list):
            qatorlar = []
        if len(qatorlar) > MAX_QATORLAR_PER_VARAQ:
            qatorlar = qatorlar[:MAX_QATORLAR_PER_VARAQ]
        varaqlar.append({"nomi": nomi, "ustunlar": ustunlar, "qatorlar": qatorlar})

    hisobot = {
        "id": f"r_{int(time.time())}_{uuid.uuid4().hex[:6]}",
        "fayl_nomi": fayl_nomi,
        "yuklangan_vaqt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "varaqlar": varaqlar,
    }

    with _lock:
        data = _load_data()
        data["hisobotlar"].insert(0, hisobot)  # eng yangisi birinchi
        if len(data["hisobotlar"]) > MAX_HISOBOTLAR:
            data["hisobotlar"] = data["hisobotlar"][:MAX_HISOBOTLAR]
        _save_data(data)

    return jsonify(hisobot)


@app.route("/api/hisobotlar/<hid>", methods=["DELETE"])
def delete_hisobot(hid):
    with _lock:
        data = _load_data()
        before = len(data["hisobotlar"])
        data["hisobotlar"] = [h for h in data["hisobotlar"] if h["id"] != hid]
        _save_data(data)
        removed = before - len(data["hisobotlar"])
    return jsonify({"ok": True, "removed": removed})


@app.route("/api/hisobotlar", methods=["DELETE"])
def clear_hisobotlar():
    with _lock:
        _save_data({"hisobotlar": []})
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
    context = context[:12000]  # AI so'roviga haddan tashqari uzun matn ketmasin

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=AI_MODEL,
            max_tokens=700,
            messages=[{
                "role": "user",
                "content": (
                    "Sen tajribali ma'lumotlar tahlilchisan. Quyida bitta Excel jadvalining "
                    "statistik xulosasi berilgan (jadval har xil mavzuda bo'lishi mumkin - "
                    "sotuv, xarajat, xodimlar, ombor va h.k. - aynan qanday mavzu ekanini "
                    "ustun nomlaridan o'zing tushunib ol). Shu statistika asosida O'ZBEK "
                    "TILIDA, qisqa (5-8 gap), aniq va amaliy xulosa yoz: asosiy tendensiya, "
                    "eng ko'zga tashlanadigan raqam(lar), xavotirli yoki g'ayrioddiy joy "
                    "bo'lsa shu, va bitta amaliy tavsiya. Faqat berilgan raqamlardan "
                    f"foydalan, hech narsa o'ylab topma:\n\n{context}"
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
