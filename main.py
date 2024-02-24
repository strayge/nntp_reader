import asyncio
import logging
import sys
from pathlib import Path


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    from .db import close_db, init_db
    from .web import run_web

    await init_db()
    try:
        await run_web()
    finally:
        await close_db()


if __name__ == '__main__':
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    sys.path.remove(str(Path(__file__).resolve().parent))
    __package__ = 'nntp_reader'

    asyncio.run(main())
