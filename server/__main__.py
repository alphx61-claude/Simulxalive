"""Run the ingestion backend: python3 -m server [--port 8787] [--contact you@example.com]"""
import asyncio
import contextlib
import logging
import signal

from . import __version__
from .config import parse_args
from .session import App
from .wsserver import serve


async def main(cfg):
    app = App(cfg, version=__version__)
    server = await serve(cfg, app.session)
    host, port = server.sockets[0].getsockname()[:2]
    logging.getLogger("simulxalive").info(
        "listening on ws://%s:%d/ws - %d axes, %d sources in the corpus%s",
        host, port, len(app.corpus.axes), len(app.corpus.sources),
        "" if cfg.contact else " (no --contact set: upstream politeness pools are off)")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    async with server:
        await stop.wait()


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")
    cfg = parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(cfg))


if __name__ == "__main__":
    run()
