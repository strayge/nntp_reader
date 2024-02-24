import asyncio
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from .config import Config
from .db import Group, Message, Thread
from .parser import update_messages

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
    threads = await group.threads.order_by("-updated").limit(100).prefetch_related("messages")
    for thread in threads:
        thread.message_count = await Message.filter(thread=thread).count()
    return templates.TemplateResponse("group.html", {"request": request, "group": group, "threads": threads})


@app.get("/threads/{thread_id}")
async def read_thread(request: Request, thread_id: str):
    thread = await Thread.get(id=thread_id).prefetch_related("group")
    messages = await thread.messages.order_by("created")
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


async def run_web() -> None:
    _ = asyncio.create_task(scheduled_update())
    uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=8080)
    uvicorn_server = uvicorn.Server(uvicorn_config)
    await uvicorn_server.serve()
