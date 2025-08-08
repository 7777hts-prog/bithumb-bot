from flask import Flask, jsonify
import worker

# Flask 앱 생성
app = Flask(__name__)

# 급등 후보 스캔 API
@app.route('/scan', methods=['GET'])
def scan():
    try:
        coins = worker.get_top_moving_coins()
        return jsonify({
            "coins": coins,
            "status": "success",
            "count": len(coins)  # 결과 개수 표시
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

# 메인 실행
if __name__ == '__main__':
    # Render 서버에서는 host='0.0.0.0' 고정, 포트는 5000
    app.run(host='0.0.0.0', port=5000)
