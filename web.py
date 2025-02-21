import asyncio
import http
import logging
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from .config import Config
from .db import Group, Thread
from .fetcher import update_messages

app = FastAPI(openapi_url=None)
config = Config()
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def read_root(request: Request):
    groups = await Group.all().order_by("name")
    return templates.TemplateResponse("index.html", {"request": request, "groups": groups})


@app.get("/groups/{group_id}")
async def read_group(request: Request, group_id: str):
    group = await Group.get(id=group_id)
    threads = await group.threads.order_by("-updated").limit(50).prefetch_related("messages")
    return templates.TemplateResponse("group.html", {"request": request, "group": group, "threads": threads})


@app.get("/threads/{thread_id}")
async def read_thread(request: Request, thread_id: str):
    thread = await Thread.get(id=thread_id).prefetch_related("group")
    messages = await thread.messages.order_by("created")
    for message in messages:
        message.body = message.body.replace("=\n", "")
        message.body = message.body.replace("=C2=A0", " ")
        for num in (0x20, 0x3D, 0x2E):
            message.body = message.body.replace(f"={num:02X}", chr(num))
    return templates.TemplateResponse("thread.html", {"request": request, "thread": thread, "messages": messages})


@app.get("/update")
async def handler_test():
    config = Config()
    await update_messages(config.groups, config.fetch_new_count, config.fetch_count)
    return 'done'


async def scheduled_update() -> None:
    config = Config()
    while True:
        try:
            await update_messages(config.groups, config.fetch_new_count, config.fetch_count)
        except Exception as e:
            logging.error(f'Error during scheduled update: {e!r}')
        await asyncio.sleep(config.fetch_interval_minutes * 60)


@app.middleware("http")
async def uvicorn_log_middleware(request: Request, call_next):
    start_time = time.monotonic()
    response = await call_next(request)
    end_time = time.monotonic()
    logger = logging.getLogger("uvicorn")
    client = f'{request.client.host}:{request.client.port}' if request.client else 'unknown'
    http_version = request.scope.get("http_version")
    method = request.method
    path = request.url.path
    code = response.status_code
    process_time = f'{(end_time - start_time):.3f}'
    try:
        code_phrase = http.HTTPStatus(code).phrase
    except ValueError:
        code_phrase = ""
    logger.info(f'{client} - "{method} {path} HTTP/{http_version}" {code} {code_phrase} {process_time}')
    return response


async def run_web() -> None:
    _ = asyncio.create_task(scheduled_update())
    uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=8080, access_log=False, log_config=None)
    uvicorn_server = uvicorn.Server(uvicorn_config)
    await uvicorn_server.serve()
