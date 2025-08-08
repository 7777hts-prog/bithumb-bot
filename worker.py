import requests

# 기존 API로 상위 변동 종목 추출
def get_top_moving_coins():
    url = "https://api.bithumb.com/public/tickers"
    res = requests.get(url).json()

    coins = []
    for symbol, data in res['data'].items():
        if symbol == 'date':
            continue
        try:
            change_rate = float(data['f24h']['change'])
            volume = float(data['acc_trade_value_24h'])
            # 필터 조건 설정 (예: 상승률 6%, 거래량)
            if change_rate >= 6 and volume > 100000000:
                coins.append({
                    "symbol": symbol,
                    "price": float(data['closing_price']),
                    "change": round(change_rate, 2),
                    "volume": volume
                })
        except:
            continue

    coins = sorted(coins, key=lambda x: x['change'], reverse=True)
    return coins[:5]

# 예측 API 호출 및 급등 가능성 높은 종목 필터링
def get_predictive_coins():
    coins = get_top_moving_coins()  # 상위 변동 종목 리스트 가져오기
    symbols = [coin['symbol'] for coin in coins]
    
    # 예측 API 호출
    url = f"https://bithumb-bot-1.onrender.com/predict?symbols={','.join(symbols)}"
    response = requests.get(url).json()
    
    predictive_coins = []
    for result in response['candidates']:
        predictive_coins.append(result['symbol'])
    
    return predictive_coins

# 실행 예시
print(get_predictive_coins())  # 급등 가능성 있는 코인 출력
