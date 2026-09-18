import flask
from .pinner import PennyPinner

app = flask.Flask(__name__)
pinner = PennyPinner("pinner.db")

@app.route("/read/<int:id>")
def read_bookmark(id):
    bookmark = pinner.get_bookmark(id)
    if not bookmark:
        return "Bookmark not found", 404
    
    return f"""
    <html>
    <body style="background-color: #333; color: #fff; font-family: sans-serif; padding: 20px;">
        <h1>{bookmark['title']}</h1>
        <p>{bookmark['content']}</p>
        <a href="/" style="color: #4CAF50;">Back</a>
    </body>
    </html>
    """

@app.route("/")
def index():
    return "<h1>PennyPinner</h1><style>body { background-color: #333; color: #fff; }</style>"

if __name__ == '__main__':
    app.run(port=8088)
