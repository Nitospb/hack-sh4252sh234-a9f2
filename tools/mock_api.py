"""Serve only a synthetic catalog and isolated state for run_mock.sh."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from recommendations.engine import Feed
from recommendations.server import handler
from service.runtime import Runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    catalog = directory / 'seed/catalog.sqlite'
    if not catalog.is_file() or not (directory / 'seed/service-assets.sqlite').is_file():
        raise SystemExit('Synthetic seed is missing')
    feed = Feed(catalog, directory / 'state/feedback.sqlite', embeddings=False)
    runtime = Runtime(feed, assets=directory / 'seed/service-assets.sqlite',
                      state=directory / 'state/service.sqlite')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(feed, runtime))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.pool.shutdown(wait=True)


if __name__ == '__main__':
    main()
