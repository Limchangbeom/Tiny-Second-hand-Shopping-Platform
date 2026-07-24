import os

from app import create_app
from app.extensions import socketio


app = create_app()


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
        allow_unsafe_werkzeug=True,
    )
