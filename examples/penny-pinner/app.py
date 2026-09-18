import flask
from .pinner import PennyPinner

app = flask.Flask(__name__)
pinner = PennyPinner("pinner.db")

@app.route("/")
def index():
    return "<h1>PennyPinner</h1><style>body { background-color: #333; color: #fff; }</style>"

if __name__ == '__main__':
    app.run(port=8088)
