import asyncio
import logging
import sys
from pathlib import Path


async def main(package_name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    from .db import close_db, init_db
    from .web import run_web

    await init_db(package_name)
    try:
        await run_web()
    finally:
        await close_db()


if __name__ == '__main__':
    directory = Path(__file__).resolve().parent
    sys.path.append(str(directory.parent))
    __package__ = str(directory.name)

    asyncio.run(main(__package__))
