from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

if __name__ == '__main__':
    print("월하 봇 시작!")
    port = int(os.environ.get('PORT', 10000))  # Render 호환 포트
    app.run(host='0.0.0.0', port=port)
