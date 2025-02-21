from tortoise import Tortoise, fields
from tortoise.fields import ForeignKeyRelation
from tortoise.models import Model


async def init_db() -> None:
    await Tortoise.init(
        db_url='sqlite://data/db.sqlite3',
        modules={'models': ['nntp_reader.db']}
    )
    await Tortoise.generate_schemas()
    await Group.all().count()  # test connection


async def close_db() -> None:
    await Tortoise.close_connections()


class Group(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=256)
    updated = fields.DatetimeField(index=True)
    threads: fields.ReverseRelation['Thread']
    messages: fields.ReverseRelation['Message']


class Thread(Model):
    id = fields.UUIDField(pk=True)
    group: ForeignKeyRelation['Group'] = fields.ForeignKeyField('models.Group', related_name='threads')
    created = fields.DatetimeField(index=True)
    updated = fields.DatetimeField(index=True)
    subject = fields.CharField(max_length=256, index=True)
    messages: fields.ReverseRelation['Message']
    references: fields.ReverseRelation['Reference']


class Message(Model):
    id = fields.UUIDField(pk=True)
    group: ForeignKeyRelation['Group'] = fields.ForeignKeyField('models.Group', related_name='messages')
    thread: ForeignKeyRelation['Thread'] | None = fields.ForeignKeyField('models.Thread', related_name='messages', null=True)
    reply_to = fields.CharField(max_length=256, null=True)
    msg_id = fields.CharField(max_length=256, unique=True, index=True)
    sender = fields.CharField(max_length=256)
    subject = fields.CharField(max_length=256)
    subject_normalized = fields.CharField(max_length=256)
    headers = fields.TextField()
    body = fields.TextField()
    created = fields.DatetimeField(index=True)

    def __repr__(self):
        return f'<Message {self.id}>'


class Reference(Model):
    id = fields.UUIDField(pk=True)
    message: ForeignKeyRelation['Message'] = fields.ForeignKeyField('models.Message', related_name='references')
    ref_msg_id = fields.CharField(max_length=256)

    def __repr__(self):
        return f'<Reference {self.id}>'
