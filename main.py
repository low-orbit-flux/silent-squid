"""Silent Squid — entry point."""

import logging
from gui import SpiderGUI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(threadName)-18s  %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    app = SpiderGUI()
    app.run()


if __name__ == "__main__":
    main()
