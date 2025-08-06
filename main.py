from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

if __name__ == '__main__':
    print("월하 봇 시작!")
    app.run(host='0.0.0.0', port=10000)
