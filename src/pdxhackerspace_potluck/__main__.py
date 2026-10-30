"""Command line: `pdxhackerspace-potluck [serve|migrate]`, or `python -m` it."""

import argparse
import contextlib
import logging
import signal
import sys
import threading
from collections.abc import Sequence
from types import FrameType

from pdxhackerspace_potluck import __version__, db
from pdxhackerspace_potluck.config import ConfigError, Settings
from pdxhackerspace_potluck.server import make_app_server

logger = logging.getLogger("pdxhackerspace_potluck")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdxhackerspace-potluck", description=__doc__)
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["serve", "migrate"],
        default="serve",
        help="serve the app (default), or apply database migrations and exit",
    )
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
    except ConfigError as e:
        parser.exit(2, f"pdxhackerspace-potluck: {e}\n")

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "migrate":
        applied = db.migrate(settings.database_url)
        logger.info("applied %d migration(s)", len(applied))
        return 0

    server = make_app_server(settings)

    # `docker stop` sends SIGTERM. Shut down cleanly instead of being killed;
    # shutdown() blocks until serve_forever() returns, so call it elsewhere.
    def stop(signum: int, frame: FrameType | None) -> None:
        logger.info("received signal %d, shutting down", signum)
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, stop)

    logger.info(
        "pdxhackerspace-potluck %s listening on %s:%d",
        __version__,
        settings.host,
        server.server_port,
    )
    with server, contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    logger.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
