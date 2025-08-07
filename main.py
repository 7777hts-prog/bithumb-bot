from flask import Flask, jsonify
import requests
import threading
import time
import os

app = Flask(__name__)

# 스캔 결과 저장용 변수
scan_result = {
    "status": "waiting",
    "coins": []
}

# 급등 조건 설정
VOLUME_THRESHOLD = 2.5   # 기준 거래량 대비 몇 배 이상
PRICE_THRESHOLD = 1.05   # 기준 대비 5% 이상 상승

# 빗썸 시세 데이터 가져오기
def fetch_market_data():
    url = "https://api.bithumb.com/public/ticker/ALL_KRW"
    try:
        response = requests.get(url, timeout=10)
        return response.json().get("data", {})
    except Exception:
        return {}

# 백그라운드 스캔 함수
def scan_market():
    global scan_result
    prev_data = fetch_market_data()

    while True:
        time.sleep(60)  # 1분 주기 스캔
        curr_data = fetch_market_data()
        rising_coins = []

        for coin, info in curr_data.items():
            if not isinstance(info, dict) or coin == "date":
                continue
            try:
                prev = prev_data.get(coin)
                if not prev:
                    continue

                prev_price = float(prev['closing_price'])
                prev_volume = float(prev['units_traded_24H'])

                curr_price = float(info['closing_price'])
                curr_volume = float(info['units_traded_24H'])

                # 급등 조건 체크
                if (curr_price > prev_price * PRICE_THRESHOLD and
                        curr_volume > prev_volume * VOLUME_THRESHOLD):
                    rising_coins.append(coin)
            except Exception:
                continue

        scan_result = {
            "status": "success",
            "coins": rising_coins
        }
        prev_data = curr_data

# 상태 확인 API
@app.route('/')
def home():
    return "Bithumb bot is running."

# 스캔 결과 API
@app.route('/scan')
def scan():
    return jsonify(scan_result)

# 서버 실행
if __name__ == '__main__':
    print("봇 시작!")
    threading.Thread(target=scan_market, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
