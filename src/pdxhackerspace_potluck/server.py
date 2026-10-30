"""The HTTP server that runs the Flask app."""

from werkzeug.serving import BaseWSGIServer, make_server

from pdxhackerspace_potluck.config import Settings
from pdxhackerspace_potluck.web import create_app


def make_app_server(settings: Settings) -> BaseWSGIServer:
    """A threaded server bound to settings.host:port (port 0 picks a free one)."""
    return make_server(
        settings.host, settings.port, create_app(settings), threaded=True
    )
