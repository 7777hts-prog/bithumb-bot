from flask import Flask, jsonify
import requests

app = Flask(__name__)

# 빗썸 전체 시세 불러오기
def fetch_bithumb_all():
    url = "https://api.bithumb.com/public/ticker/ALL_KRW"
    r = requests.get(url, timeout=10)
    return r.json().get("data", {})

# 완화 조건 적용 (거래량 기준 20% 낮춤, 상승률 4.5% 이상)
def pick_hot_coins(data):
    out = []
    for sym, info in data.items():
        if not isinstance(info, dict):
            continue
        try:
            chg = float(info.get("fluctate_rate_24H", 0))  # 24시간 변동률(%)
            vol = float(info.get("units_traded_24H", 0))   # 24시간 거래량
            last = float(info.get("closing_price", 0))     # 현재가

            # 조건: 상승률 > 4.5% & 거래량 > 800,000
            if chg > 4.5 and vol > 800_000:
                out.append({
                    "symbol": sym,
                    "change": chg,
                    "volume": vol,
                    "price": last
                })
        except Exception:
            continue
    return out

# /scan API
@app.route("/scan", methods=["GET"])
def scan():
    data = fetch_bithumb_all()
    coins = pick_hot_coins(data)
    return jsonify({"coins": coins, "status": "success"})

# 기본 루트
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
