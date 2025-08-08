import os, time, json, requests

WEB_URL  = os.getenv("WEB_URL")      # 추후 /update 연결시 사용
API_KEY  = os.getenv("API_KEY")      # main.py와 같은 값
INTERVAL = int(os.getenv("INTERVAL_SECONDS", "600"))  # 초 단위, 기본 10분

def fetch_bithumb_all():
    url = "https://api.bithumb.com/public/ticker/ALL_KRW"
    r = requests.get(url, timeout=10)
    return r.json().get("data", {})

def pick_hot_coins(data):
    out = []
    for sym, info in data.items():
        if not isinstance(info, dict): 
            continue
        try:
            chg  = float(info.get("fluctate_rate_24H", 0.0))   # 24h 변동률 %
            vol  = float(info.get("units_traded_24H", 0.0))    # 24h 거래량
            last = float(info.get("closing_price", 0.0))

            # 📌 조금 완화된 조건
            # 거래량 기준 기존보다 20% 낮춤, 상승률 기준 0.5% 낮춤
            if chg > 4.5 and vol > 800_000 and last > 0:
                out.append(sym)

        except Exception:
            continue
    return out

def push_to_web(coins):
    print("SCAN:", coins[:20])
    # 나중에 /update 연결할 때 아래 코드 활성화
    # headers = {"X-API-KEY": API_KEY, "Content-Type":"application/json"}
    # payload = {"coins": coins, "status": "success"}
    # requests.post(f"{WEB_URL}/update", headers=headers, data=json.dumps(payload), timeout=10)

if __name__ == "__main__":
    while True:
        try:
            data  = fetch_bithumb_all()
            coins = pick_hot_coins(data)
            push_to_web(coins)
        except Exception as e:
            print("ERR:", e)
        time.sleep(INTERVAL)
