# -*- coding: utf-8 -*-
import os
import requests

TIMEOUT = 8
BASE = "https://bithumb-bot-1.onrender.com"
BOT = os.getenv("TG_BOT_TOKEN")
CHAT = os.getenv("TG_CHAT_ID")
SESS = requests.Session()

def get_top_moving_coins():
    res = SESS.get("https://api.bithumb.com/public/tickers", timeout=TIMEOUT).json()
    coins = []
    for symbol, data in res.get('data', {}).items():
        if symbol == 'date': continue
        try:
            change_rate = float(data['f24h']['change'])
            volume = float(data['acc_trade_value_24h'])
            if change_rate >= 6 and volume > 100000000:
                coins.append({"symbol": symbol,"price": float(data['closing_price']),"change": round(change_rate, 2),"volume": volume})
        except:
            continue
    coins.sort(key=lambda x: x['change'], reverse=True)
    return coins[:5]

def get_predictive_coins():
    coins = get_top_moving_coins()
    if not coins: return []
    symbols = [c['symbol'] for c in coins]
    r = SESS.get(f"{BASE}/predict", params={'symbols': ','.join(symbols)}, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    return [c['symbol'] for c in j.get('candidates', [])]

def send_telegram(text):
    if not (BOT and CHAT): return
    SESS.post(f"https://api.telegram.org/bot{BOT}/sendMessage", json={"chat_id": CHAT, "text": text}, timeout=TIMEOUT)

def run_once():
    preds = get_predictive_coins()
    if not preds:
        print("[worker] no predictive candidates")
        return
    msg = "✅ 급등 전 후보 감지\n" + "\n".join(f"• {s}" for s in preds)
    print(msg)
    send_telegram(msg)

if __name__ == "__main__":
    run_once()
