from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

@app.route('/scan')
def scan():
    # 실제 급등 코인 리스트가 여기 들어갈 수 있음
    return jsonify({
        'status': 'success',
        'coins': ['PENGU', 'TRUMP', 'FLR']
    })

if __name__ == '__main__':
    print("월하 봇 시작!")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
