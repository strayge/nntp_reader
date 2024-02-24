import asyncio
import logging
from collections import defaultdict

import pytest

from ..async_nntplib import AsyncNNTP


class NNTPServer:
    def __init__(self, host: str = '127.0.0.1', port: int = 30888) -> None:
        self.host = host
        self.port = port
        self.server: asyncio.Server = None
        self.commands_count: dict[str, int] = defaultdict(int)
        self.logger = logging.getLogger('server')

    async def start(self) -> None:
        self.server = await asyncio.start_server(self.on_message, self.host, self.port)

    async def stop(self) -> None:
        if not self.server:
            return
        self.server.close()
        await asyncio.sleep(0)

    async def on_message(self, reader, writer) -> None:
        writer.write(b'201 nntp.lore.kernel.org ready - post via email\r\n')
        await writer.drain()
        while data := await reader.read(4096):
            self.logger.info(f'server received: {data!r}')
            reply = self.get_reply(data)
            self.logger.info(f'server sending: {reply!r}')
            writer.write(reply)
            await writer.drain()

    def get_over_resp_msg(self, msg_num: int, subject: str | None = None) -> bytes:
        subject = subject or f"[NUM {msg_num}] [PATCH] subject"
        author = 'Viresh Kumar <viresh.kumar@linaro.org>'
        date = 'Fri, 08 Dec 2023 10:18:01 +0000'
        msg_id = f'<{msg_num}.something@test.test>'
        size = '5347'
        lines = '34'
        xrefs = ['nntp.lore.kernel.org org.kernel.vger.rust-for-linux:5549', 'org.kernel.vger.linux-doc:94346 org.kernel.vger.linux-kernel:5069858']
        line = f"{msg_num}\t{subject}\t{author}\t{date}\t{msg_id}\t\t{size}\t{lines}\tXref: {' '.join(xrefs)}\r\n"
        return line.encode()

    def get_article_resp(self, msg_id: str, msg_num: int = 1000) -> bytes:
        if msg_id.endswith('@test.test>'):
            msg_num = int(msg_id.split('.')[0][1:])
        date = 'Fri, 08 Dec 2023 09:48:30 +0000'
        author = 'Benno Lossin <benno.lossin@proton.me>'
        subject = f"[NUM {msg_num}] [PATCH] subject"
        reply_msg_id = '<20231206-alice-file-v2-1-af617c0d9d94@google.com>'
        resp_lines = [
            f'220 {msg_num} {msg_id} article retrieved - head and body follow',
            f'Date: {date}',
            'To: Alice Ryhl <aliceryhl@google.com>',
            f'From: {author}',
            f'Subject: {subject}',
            f'Message-ID: {msg_id}',
            f'In-Reply-To: {reply_msg_id}',
            f'References: <20231206-alice-file-v2-0-af617c0d9d94@google.com> {reply_msg_id}',
            'X-Mailing-List: rust-for-linux@vger.kernel.org',
            'List-Id: <rust-for-linux.vger.kernel.org>',
            'Content-Type: text/plain; charset=utf-8',
            'Content-Transfer-Encoding: quoted-printable',
            'Xref: nntp.lore.kernel.org org.kernel.vger.rust-for-linux:5548',
            '\torg.kernel.vger.linux-fsdevel:269104',
            '\torg.kernel.vger.linux-kernel:5069838',
            'Newsgroups: org.kernel.vger.rust-for-linux,org.kernel.vger.linux-fsdevel,org.kernel.vger.linux-kernel',
            'Path: nntp.lore.kernel.org!not-for-mail',
            '',
            'On 12/6/23 12:59, Alice Ryhl wrote:',
            '> +impl File {',
            'The comment should also justify the cast.',
            '',
            '--=20',
            'Cheers,',
            'Benno',
            '.',
        ]
        return '\r\n'.join(resp_lines).encode() + b'\r\n'

    def get_reply(self, data: bytes) -> bytes:
        if data == b'CAPABILITIES\r\n':
            self.commands_count['CAPABILITIES'] += 1
            return b'101 Capability list:\r\nVERSION 2\r\nREADER\r\nNEWNEWS\r\nLIST ACTIVE ACTIVE.TIMES NEWSGROUPS OVERVIEW.FMT\r\nHDR\r\nOVER\r\nCOMPRESS DEFLATE\r\n.\r\n'
        if data.startswith(b'GROUP ') and data.endswith(b'\r\n'):
            self.commands_count['GROUP'] += 1
            group = data.decode().split()[1]
            last_msg_num = 1000
            if group.isdigit():
                last_msg_num = int(group)
            resp = f'211 {last_msg_num - 1} 1 {last_msg_num} {group}\r\n'
            return resp.encode()
        if data.startswith(b'LIST OVERVIEW.FMT\r\n'):
            self.commands_count['LIST OVERVIEW.FMT'] += 1
            return b'215 information follows\r\nSubject:\r\nFrom:\r\nDate:\r\nMessage-ID:\r\nReferences:\r\nBytes:\r\nLines:\r\nXref:full\r\n.\r\n'
        if data.startswith(b'OVER ') and data.endswith(b'\r\n'):
            self.commands_count['OVER'] += 1
            num1, num2 = data.decode().split()[1].split('-')
            resp = b'224 Overview information follows\r\n'
            for num in range(int(num1), int(num2) + 1):
                resp += self.get_over_resp_msg(num)
            resp += b'.\r\n'
            return resp
        if data.startswith(b'ARTICLE ') and data.endswith(b'\r\n'):
            self.commands_count['ARTICLE'] += 1
            msg_id = data.decode().split()[1]
            return self.get_article_resp(msg_id)
        return b'400 Command not implemented\r\n'


@pytest.fixture
async def nntp_server():
    server = NNTPServer()
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def test_last_messages_without_limit(nntp_server: NNTPServer) -> None:
    nntp = AsyncNNTP(nntp_server.host, port=nntp_server.port)
    await nntp.connect()
    assert nntp_server.commands_count['CAPABILITIES'] == 1
    messages = await nntp.last_messages(group='10', count=2, last_msg_id=None)
    assert nntp_server.commands_count['GROUP'] == 1
    assert nntp_server.commands_count['OVER'] == 1
    assert nntp_server.commands_count['ARTICLE'] == 2
    assert len(messages) == 2
    assert messages[0]['subject'].startswith('[NUM 9]')
    assert messages[1]['subject'].startswith('[NUM 10]')


async def test_last_messages_with_limit(nntp_server: NNTPServer) -> None:
    nntp = AsyncNNTP(nntp_server.host, port=nntp_server.port)
    await nntp.connect()
    messages = await nntp.last_messages(group='10', count=5, last_msg_id='<8.something@test.test>')
    assert nntp_server.commands_count['ARTICLE'] == 2
    assert len(messages) == 2
    assert messages[0]['subject'].startswith('[NUM 9]')
    assert messages[1]['subject'].startswith('[NUM 10]')


async def test_last_messages_chunked(nntp_server: NNTPServer) -> None:
    nntp = AsyncNNTP(nntp_server.host, port=nntp_server.port)
    await nntp.connect()
    messages = await nntp.last_messages(group='1000', count=500, last_msg_id='<850.something@test.test>')
    assert nntp_server.commands_count['OVER'] == 2
    assert nntp_server.commands_count['ARTICLE'] == 150
    assert len(messages) == 150
    assert messages[0]['subject'].startswith('[NUM 851]')
    assert messages[-1]['subject'].startswith('[NUM 1000]')
