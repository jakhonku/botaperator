# Operatorlar uchun Telegram bot

Foydalanuvchilar bot orqali savol yuboradi, bot esa bo'sh operatorni topib ularni bir-biriga ulaydi. Operator va foydalanuvchi shu bot orqali bir-biriga xabar yozishadi. 40+ operator bilan ishlash uchun mo'ljallangan.

## Xususiyatlari

- ✅ Foydalanuvchi savol yuboradi → bo'sh operator avtomatik ulanadi
- ✅ Barcha operatorlar band bo'lsa — foydalanuvchi **navbatga** qo'yiladi, operator bo'shashi bilan avtomatik ulanadi
- ✅ Matn, rasm, video, fayl, audio — barchasi uzatiladi
- ✅ Operator `🟢 Ishga kirishish` / `🔴 Ishdan chiqish` tugmalari bilan holatini boshqaradi
- ✅ Operator bir vaqtda faqat bitta suhbatda bo'ladi (ortiqcha yuklanmaydi)
- ✅ Admin panelidan operatorlarni qo'shish/o'chirish, statistika, broadcast
- ✅ SQLite — qayta ishga tushgandan keyin holat saqlanib qoladi

## O'rnatish

**Python 3.10+ kerak.**

```bash
pip install -r requirements.txt
```

`.env.example` ni `.env` ga ko'chiring va tokenni kiriting:

```
BOT_TOKEN=123456789:AAA...
ADMIN_IDS=111111111
DB_PATH=bot.db
```

- `BOT_TOKEN` — [@BotFather](https://t.me/BotFather) dan olgan token
- `ADMIN_IDS` — admin(lar) Telegram ID si (vergul bilan ajrating). O'z ID ingizni bilish uchun botda `/myid` yozing

## Ishga tushirish

```bash
python bot.py
```

## Foydalanish

### 1. Admin

Adminlik `.env` dagi `ADMIN_IDS` bilan aniqlanadi.

| Buyruq | Vazifasi |
|---|---|
| `/addoperator <tg_id> <Ism Familiya>` | Operator qo'shish |
| `/removeoperator <tg_id>` | Operatorni o'chirish |
| `/operators` | Barcha operatorlar ro'yxati |
| `/stats` | Statistika |
| `/broadcast <matn>` | Barcha operatorlarga xabar yuborish |
| `/myid` | O'z Telegram ID ni ko'rish |

**Muhim:** Operator qo'shishdan oldin, u kishi botda `/start` bosib, o'z ID ni `/myid` orqali olishi kerak. Keyin admin `/addoperator <uning_id> <Ismi>` qiladi.

### 2. Operator

1. Admin qo'shgandan keyin botga `/start` yuboradi
2. `🟢 Ishga kirishish` tugmasini bosadi — onlayn bo'ladi
3. Foydalanuvchi kelganda avtomatik ulanadi — bot savolni ko'rsatadi
4. Javob yozadi, kerak bo'lsa rasm/fayl yuboradi
5. Tugagach `✅ Suhbatni yakunlash` tugmasini bosadi — keyingi navbatchi avtomatik ulanadi
6. Ishdan chiqish uchun `🔴 Ishdan chiqish`

### 3. Foydalanuvchi

1. Botga `/start` yuboradi
2. Savolini yozadi
3. Bo'sh operatorga ulanadi (yoki navbatda kutadi)
4. Javob olgandan keyin `❌ Suhbatni yakunlash` bosadi

## Arxitektura

- `bot.py` — asosiy kirish nuqtasi, handlerlar, yo'naltirish logikasi
- `database.py` — SQLite (aiosqlite) orqali ma'lumotlar bazasi
- `keyboards.py` — Reply tugmalar
- `config.py` — `.env` dan sozlamalarni yuklash

### Ma'lumotlar bazasi

**operators** — operatorlar ro'yxati (tg_id, ism, onlayn holat)
**chats** — har bir suhbat (status: `waiting` / `active` / `ended`)

Suhbatni yo'naltirish oddiy sxemada ishlaydi:
- Foydalanuvchining **aktiv** chati bor → xabar operatorga `copy_message` orqali uzatiladi
- Operatorning **aktiv** chati bor → xabar foydalanuvchiga uzatiladi
- Chat yo'q → foydalanuvchi birinchi xabari yangi suhbat boshlaydi

Operator va foydalanuvchi bir-birining haqiqiy Telegram ID sini **ko'rmaydi** — xabarlar bot orqali uzatiladi.

## Kengaytirish g'oyalari

Keyingi bosqichlarda qo'shish mumkin:

- Operator baholash (5 yulduzli sistema)
- Chat tarixi arxivi (hozir yakunlangan chatlar DB da saqlanadi, admin uchun interfeys qo'shsa bo'ladi)
- Bir operator bir vaqtda bir nechta suhbat olishi (concurrent chats limit)
- Bo'limlar bo'yicha operatorlarga yo'naltirish (Sotuv/Texnik/Buxgalteriya)
- Tilni tanlash (O'zbekcha / Ruscha)
- Webhook rejimi (produksiya uchun)

## Produksiyada ishga tushirish

### systemd (Linux)

`/etc/systemd/system/tg-support-bot.service`:

```ini
[Unit]
Description=Telegram support bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/tg-support-bot
ExecStart=/opt/tg-support-bot/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now tg-support-bot
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```
