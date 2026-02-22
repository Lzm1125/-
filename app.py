from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return "首页运行成功！"

if __name__ == '__main__':
    app.run(debug=True)
