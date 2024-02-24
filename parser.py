import logging
import re
from collections import defaultdict
from datetime import datetime
from uuid import uuid4

from tortoise.transactions import in_transaction

from .async_nntplib import AsyncNNTP
from .db import Group, Message, Reference, Thread


async def get_or_create_group(name: str) -> Group:
    group = await Group.get_or_none(name=name)
    if group is None:
        group = await Group.create(name=name, updated=datetime.now())
    return group


async def set_threads_for_messages(messages: list[Message]) -> list[Thread]:
    thread_by_subject: dict[str, Thread] = {}
    thread_by_msg_id: dict[str, Thread] = {}
    new_threads = []
    for message in messages:
        thread = None
        if message.reply_to:
            if message.reply_to in thread_by_msg_id:
                thread = thread_by_msg_id[message.reply_to]
            elif prev_message := await Message.filter(msg_id=message.reply_to).first():
                thread = Thread.get(id=prev_message.thread_id)
        if not thread and message.subject_normalized in thread_by_subject:
            thread = thread_by_subject[message.subject_normalized]
        if not thread:
            thread = await Thread.filter(
                subject=message.subject_normalized,
                group=message.group,
            ).first()
        if not thread:
            thread = Thread(
                id=uuid4(),
                group=message.group,
                subject=message.subject_normalized,
                created=message.created,
                updated=message.created,
            )
            new_threads.append(thread)

        thread_by_subject[message.subject_normalized] = thread
        thread_by_msg_id[message.msg_id] = thread
        message.thread = thread
    return new_threads


async def save_messages(messages: list[Message], references: list[Reference]) -> None:
    new_threads = await set_threads_for_messages(messages)
    async with in_transaction() as transaction:
        await Thread.bulk_create(new_threads, using_db=transaction)
        await Message.bulk_create(messages, using_db=transaction)
        await Reference.bulk_create(references, using_db=transaction)


def normalize_subject(subject: str) -> str:
    """Remove 're:' and 'fwd:' prefixes and patch numbers from subject.

    >>> normalize_subject('Re: [PATCH v2 1/2] foo')
    '[patch v2] foo'
    >>> normalize_subject('Fwd: Re: [PATCH 1/2] bar')
    '[patch] bar'
    """
    subject = subject.lower()
    subject = re.sub(r'\s+', ' ', subject).strip()
    subject = re.sub(r'^(re: |fwd: )+', '', subject)
    for match_groups in re.findall(r'(\[[^\]]*?patch[^\]]*?(\s+\d+(\/\d+)?)\])', subject):
        match, numbers, _ = match_groups
        new_match = match.replace(numbers, '')
        subject = subject.replace(match, new_match)
    return subject


async def update_messages(groups_urls: list[str], fetch_new: int, fetch_old: int) -> None:
    groups_per_server = defaultdict(list)
    for group_url in groups_urls:
        server, group = group_url.split('/', 1)
        groups_per_server[server].append(group)
    logging.info(f'Updating messages for {len(groups_per_server)} servers')
    for server, groups in groups_per_server.items():
        try:
            nntp = AsyncNNTP(server, debug=False)
            await nntp.connect()
            for group_name in groups:
                db_group = await get_or_create_group(group_name)
                last_msg = await Message.filter(group=db_group).order_by('-created').first()
                lst_msg_id = last_msg.msg_id if last_msg else None
                limit = fetch_old if lst_msg_id else fetch_new
                nntp_msgs = await nntp.last_messages(group_name, limit, lst_msg_id, chunk_size=50)

                messages = []
                references = []
                for msg in nntp_msgs:
                    msg['date'] = datetime.strptime(msg['date'], '%a, %d %b %Y %H:%M:%S %z')
                    reply_to = None
                    for header in msg['headers']:
                        if header.lower().startswith('in-reply-to:'):
                            reply_to = header.split(':', 1)[1].strip()
                    message = Message(
                        id=uuid4(),
                        group=db_group,
                        msg_id=msg['message-id'],
                        reply_to=reply_to,
                        sender=msg['from'],
                        subject=msg['subject'],
                        subject_normalized=normalize_subject(msg['subject']),
                        headers='\n'.join(msg['headers']),
                        body='\n'.join(msg['body']),
                        created=msg['date'],
                    )
                    if await Message.filter(msg_id=message.msg_id).exists():
                        continue
                    messages.append(message)
                    for ref in msg['references']:
                        references.append(Reference(
                            id=uuid4(),
                            message_id=message.id,
                            ref_msg_id=ref,
                        ))
                if messages:
                    logging.info(f'Saving {len(messages)} messages for {group_name}')
                    await save_messages(messages, references)
                else:
                    logging.info(f'No new messages for {group_name}')
        except Exception as e:
            logging.error(f'Error connecting to {server}: {e}')
            raise
