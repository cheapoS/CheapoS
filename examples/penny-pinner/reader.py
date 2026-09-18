from .pinner import PennyPinner

def generate_html(bookmark):
    return f"""
    <html>
    <body style="background-color: #333; color: #fff; font-family: sans-serif; padding: 20px;">
        <h1>{bookmark['title']}</h1>
        <p>{bookmark['content']}</p>
        <a href="/" style="color: #4CAF50;">Back</a>
    </body>
    </html>
    """

def create_app(db_path="pinner.db"):
    import flask
    app = flask.Flask(__name__)
    setattr(app, 'pinner', PennyPinner(db_path))
    @app.route("/read/<int:id>")
    def read_bookmark(id):
        bookmark = app.pinner.get_bookmark(id)
        if not bookmark:
            return "Bookmark not found", 404
        return generate_html(bookmark)

    @app.route("/")
    def index():
        return "<h1>PennyPinner</h1><style>body { background-color: #333; color: #fff; }</style>"
    return app
