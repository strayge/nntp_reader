import asyncio
import logging


class AsyncNNTP:
    LONG_RESPONSES = ('100', '101', '211', '215', '220', '221', '222', '224', '225', '230', '231', '282')

    def __init__(self, host: str, port: int = 119, debug: bool = False) -> None:
        self.host = host
        self.port = port
        self.debug = debug
        self.logger = logging.getLogger('nntp')
        self.sock_reader: asyncio.StreamReader = None
        self.sock_writer: asyncio.StreamWriter = None
        self.caps: dict[str, list[str]] = {}
        self.fmt_fields: list[str] = []

    async def _create_connection(self) -> None:
        self.sock_reader, self.sock_writer = await asyncio.open_connection(self.host, self.port)

    async def connect(self) -> None:
        await self._create_connection()
        await self._read_resp()  # welcome message
        await self._get_caps()

    async def _read_resp(self, long: bool = False) -> list[str]:
        resp_raw = await self.sock_reader.readline()
        self.logger.debug(f'<< {resp_raw!r}')
        resp = resp_raw.decode()
        if resp.endswith('\r\n'):
            resp = resp[:-2]
        if not resp or resp[0] in '45':
            raise ValueError(f'NNTP error: {resp}')
        lines = [resp]
        if resp[:3] not in self.LONG_RESPONSES or not long:
            if self.debug:
                self.logger.info(f'short response: {resp}')
            return lines
        while line_raw := await self.sock_reader.readline():
            self.logger.debug(f'<< {line_raw!r}')
            line = line_raw.decode(errors='ignore')
            if not line or line in ('.\n', '.\r\n'):
                break
            if line.endswith('\r\n'):
                line = line[:-2]
            lines.append(line)
        if self.debug:
            self.logger.info(f'long response: {lines}')
        return lines

    async def _send_cmd(self, cmd: str, long: bool) -> list[str]:
        if self.debug:
            self.logger.info(f'sending: {cmd}')
        cmd_raw = cmd.encode() + b'\r\n'
        self.logger.debug(f'>> {cmd_raw!r}')
        self.sock_writer.write(cmd_raw)
        return await self._read_resp(long=long)

    async def _send_short_cmd(self, cmd: str) -> str:
        resp = await self._send_cmd(cmd, False)
        return resp[0]

    async def _send_long_cmd(self, cmd: str) -> list[str]:
        return await self._send_cmd(cmd, True)

    async def _get_caps(self) -> None:
        resp = await self._send_long_cmd('CAPABILITIES')
        caps = {}
        for line in resp[1:]:
            words = line.split()
            caps[words[0]] = words[1:]
        self.caps = caps

    async def _get_list_overview_fmt(self) -> None:
        try:
            resp = await self._send_long_cmd('LIST OVERVIEW.FMT')
            fmt_fields = []
            for line in resp[1:]:
                parts = line.split(':')
                name = parts[0] if parts[0] else parts[1]
                fmt_fields.append(name.lower())
        except ValueError:
            fmt_fields = ['subject', 'from', 'date', 'message-id', 'references', 'bytes', 'lines']
        self.fmt_fields = fmt_fields

    async def list_groups(self) -> list[str]:
        resp = await self._send_long_cmd('LIST')
        groups = []
        for line in resp[1:]:
            name, _ = line.split(' ', 1)
            groups.append(name)
        return groups

    async def group(self, group: str) -> tuple[int, int, int, str]:
        resp = await self._send_short_cmd(f'GROUP {group}')
        words = resp.split()
        if words[0] != '211':
            raise ValueError(f'NNTP error: {resp}')
        count = int(words[1]) if len(words) > 1 else 0
        first = int(words[2]) if len(words) > 2 else 0
        last = int(words[3]) if len(words) > 3 else 0
        name = words[4] if len(words) > 4 else ''
        return count, first, last, name

    async def over(self, first: int, last: int) -> list[dict]:
        if not self.fmt_fields:
            await self._get_list_overview_fmt()
        cmd = 'OVER' if 'OVER' in self.caps else 'XOVER'
        resp = await self._send_long_cmd(f'{cmd} {first}-{last}')
        messages = []
        for line in resp[1:]:
            msg = {}
            parts = line.split('\t')
            for i in range(min(len(self.fmt_fields), len(parts) - 1)):
                field_name = self.fmt_fields[i]
                value = parts[i + 1]
                if value[:len(field_name) + 1].lower() == field_name + ':':
                    value = value[len(field_name) + 1:].lstrip()
                msg[field_name] = value
            messages.append(msg)
        return messages

    async def article(self, message_id: str) -> tuple[list[str], list[str]]:
        resp = await self._send_long_cmd(f'ARTICLE {message_id}')
        headers = []
        body = []
        body_started = False
        for line in resp[1:]:
            if not line:
                body_started = True
                continue
            if body_started:
                body.append(line)
            else:
                headers.append(line)
        return headers, body

    async def body(self, message_id: str) -> list[str]:
        resp = await self._send_long_cmd(f'BODY {message_id}')
        return resp[1:]

    async def last_messages(
        self,
        group: str,
        count: int,
        last_msg_id: str | None = None,
        chunk_size: int = 100,
    ) -> list[dict]:
        _, first_msg_num_in_group, last_msg_num, _ = await self.group(group)
        first_msg_num = max(first_msg_num_in_group, last_msg_num - count + 1)
        messages = []
        for chunk_end in range(last_msg_num, first_msg_num - 1, -chunk_size):
            chunk_start = max(first_msg_num, chunk_end - chunk_size + 1)
            over_messages = await self.over(chunk_start, chunk_end)
            ended = False
            for msg in over_messages[::-1]:
                if last_msg_id and msg['message-id'] == last_msg_id:
                    ended = True
                    break
                msg['headers'], msg['body'] = await self.article(msg['message-id'])
                if 'references' in msg:
                    msg['references'] = msg['references'].split()
                messages.append(msg)
            if ended:
                break
        return messages[::-1]
