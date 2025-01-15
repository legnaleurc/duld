import asyncio
import sys

from .main import Daemon


main = Daemon(sys.argv)
sys.exit(asyncio.run(main()))
