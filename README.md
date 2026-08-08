# Moliya Daftari — Sayt (Rahbarlar uchun)

Kunlik sotuv/tushum/xarajat ma'lumotlarini yuklab, AI orqali xulosa oladigan sayt. Barcha rahbarlar bitta havola orqali kiradi va bir xil ma'lumotni ko'radi.

## Qanday ishlaydi

```
Brauzer (rahbar)  →  Sizning serveringiz (Flask)  →  Anthropic API
                         ↑
                    API kalit shu yerda,
                    hech qachon brauzerga chiqmaydi
```

- `app.py` — server: saytni ko'rsatadi, ma'lumotni saqlaydi, AI so'rovini xavfsiz yuboradi
- `static/index.html` — saytning ko'rinishi (frontend)
- `data.json` — barcha yuklangan moliyaviy yozuvlar shu yerda saqlanadi (server o'zi yaratadi)

## 1. Anthropic API kalitini oling

console.anthropic.com → API Keys → yangi kalit yarating.

> Eslatma: bu pullik xizmat — har bir AI so'rov bir necha tiyin turadi. Oyiga bir necha ming so'rov uchun xarajat juda kichik bo'ladi, lekin balansni kuzatib turing.

## 2. Mahalliy kompyuterda sinash (ixtiyoriy)

```
cd moliya_sayt
pip install -r requirements.txt
copy .env.example .env
```
`.env` faylni ochib, `ANTHROPIC_API_KEY` ni to'ldiring, so'ng:
```
python app.py
```
Brauzerda `http://localhost:5000` ni oching.

## 3. Internetga chiqarish — Render.com orqali (bepul, tavsiya etiladi)

### a) GitHub'ga yuklash
1. github.com'da yangi repository yarating (masalan `moliya-daftari`)
2. Shu papkadagi barcha fayllarni (`.env`dan tashqari!) shu repositoryga yuklang

### b) Render.com'da sozlash
1. render.com'da ro'yxatdan o'ting (GitHub akkaunti bilan kirish mumkin)
2. **New +** → **Web Service** ni tanlang
3. GitHub repositoryingizni ulang
4. Sozlamalar:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Free
5. **Environment Variables** bo'limida qo'shing:
   - `ANTHROPIC_API_KEY` = sizning haqiqiy kalitingiz
   - `AI_MODEL` = `claude-sonnet-5`
6. **Create Web Service** ni bosing

3-5 daqiqada sayt tayyor bo'ladi, sizga shunday havola beriladi:
```
https://moliya-daftari.onrender.com
```

Shu havolani rahbarlaringizga yuboring — telefon yoki kompyuterdan ochib, to'g'ridan-to'g'ri ishlata olishadi.

> **Eslatma (bepul reja haqida):** Render'ning bepul rejasida sayt 15 daqiqa ishlatilmasa "uxlab qoladi" va keyingi ochilishda 30-50 soniya sekinroq yuklanadi. Bu jiddiy muammo bo'lsa, keyinroq pullik ($7/oy) rejaga o'tish mumkin — u doim tayyor turadi.

## 4. Muqobil variant — Railway.app

Render o'rniga Railway.app ham xuddi shunday ishlaydi (GitHub ulash → environment variable qo'shish → deploy). Railway'da bepul limit oz (oyiga ~5$ kredit), lekin "uxlab qolish" muammosi yo'q.

## Xavfsizlik eslatmalari

- `.env` faylni **hech qachon** GitHub'ga yuklamang (unda API kalit bor). GitHub'ga yuklashdan oldin `.gitignore` fayl yarating va ichiga `.env` deb yozing.
- Hozircha sayt **hamma uchun ochiq** (havolani bilgan har kim kira oladi). Agar faqat rahbarlar kira olishini istasangiz, sodda parol himoyasini qo'shishimiz mumkin — buni alohida so'rang.
- `data.json` fayl serverda saqlanadi. Render/Railway'ning bepul rejasida disk vaqti-vaqti bilan tozalanishi mumkin — muhim ma'lumot uchun uzoq muddatda haqiqiy bazaga (masalan PostgreSQL) o'tish tavsiya etiladi.

## Loyiha tuzilishi

```
moliya_sayt/
├── app.py              # Flask server
├── requirements.txt     # Python kutubxonalari
├── .env.example          # Sozlamalar namunasi
├── static/
│   └── index.html         # Sayt ko'rinishi (React + Chart.js)
└── data.json             # Ma'lumotlar (avtomatik yaratiladi)
```

## Keyingi qadamlar

- Parol bilan himoyalash (faqat rahbarlar kirishi uchun)
- Haqiqiy ma'lumotlar bazasiga o'tish (PostgreSQL) — ma'lumot yo'qolmasligi kafolati uchun
- Excel eksport tugmasi qo'shish
- Kunlik avtomatik email/Telegram xabar yuborish
