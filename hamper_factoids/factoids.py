import json
import re
from random import random

from ometa.runtime import ParseError
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

from hamper.interfaces import ChatCommandPlugin, Command
from hamper_factoids.parser import learn_grammar
# from hamper.utils import ude


SQLAlchemyBase = declarative_base()


class Factoids(ChatCommandPlugin):
    """Second generation of Factoids."""

    name = 'factoids2'
    priority = 2

    def setup(self, loader):
        super(Factoids, self).setup(loader)
        self.db = loader.db
        SQLAlchemyBase.metadata.create_all(self.db.engine)
        self.load_factoids()

    def load_factoids(self):
        self.factoids = []
        raw_factoids = (self.db.session.query(RawField)
                        .filter(RawField.kind == 'factoid'))

        for raw in raw_factoids:
            factoid = {
                'id': raw.id,
                'trigger': None,
                'probability': 1,
                'action': 'say',
                'response': None,
            }
            factoid.update(json.loads(raw.data))
            self.factoids.append(factoid)

        self.factoids = [self.upgrade_factoid(f) for f in self.factoids
                         if f['trigger'] and f['response']]

    def upgrade_factoid(self, factoid_dict, type='is'):
        factoid = {
            'trigger': None,
            'probability': 1,
            'action': 'say',
            'response': None,
        }
        factoid.update(factoid_dict)
        match = re.match(r'^/(.*)/(i?)', factoid['trigger'])
        if match:
            flags = 0
            if 'i' in match.group(2):
                flags |= 0
            factoid['trigger'] = re.compile(match.group(1), flags)
        else:
            factoid['trigger'] = NotRegex(factoid['trigger'], type)
        return factoid

    def add_factoid(self, factoid_dict, factoid_type='is'):
        """Add an un-upgraded factoid to the db and the in-memory store."""
        factoid = self.upgrade_factoid(factoid_dict, factoid_type)
        self.factoids.append(factoid)
        factoid_orm = RawField('factoid', json.dumps(factoid_dict))
        self.db.session.add(factoid_orm)
        self.db.session.commit()
        factoid['id'] = factoid_orm.id

    def message(self, bot, comm):
        matched = []
        message = comm['message'].strip()

        for factoid in self.factoids:
            match = factoid['trigger'].match(message)
            if match:
                matched.append(factoid)

        if matched:
            # Now look through all of them, taking in to account probabilities
            choice = random() * len(matched)
            for factoid in matched:
                choice -= factoid['probability']
                if choice < 0:
                    self.send_factoid(bot, comm, factoid)
                    return True

        # Welp, nothing matched.
        return super(Factoids, self).message(bot, comm)

    def send_factoid(self, bot, comm, factoid):
        if factoid['action'] == 'say':
            bot.reply(comm, factoid['response'])
        elif factoid['action'] == 'reply':
            bot.reply(comm, '{user}: {0}'.format(factoid['response'], **comm))
        elif factoid['action'] in ['me', 'emote', 'act', 'action']:
            bot.me(comm, factoid['response'])
        else:
            bot.reply(comm, 'Unknown action "{action}" on factoid {id}'
                      .format(**factoid))

    # Because this command is defined first, it will be checked first,
    class ClassicLearn(Command):
        """Learn a factoid."""
        name = 'learn'
        regex = (r'learn(?:\s+that)?\s+(?P<trigger>.+)\s+(?P<type>\w+)\s+'
                 r'<(?P<action>\w+)>\s+(?P<response>.*)')

        def command(self, bot, comm, groups):
            bot.reply(comm, 'hmm {0}'.format(groups))
            factoid = {
                'trigger': groups['trigger'],
                'action': groups['action'],
                'response': groups['response'],
            }
            self.plugin.add(factoid, groups['type'])
            bot.reply(comm, "{user}: Well, ok, but that's the old way."
                      .format(**comm))
            return True

    class ModernLearn(Command):
        name = 'modern learn'
        regex = r'^learn\s+(.*=.*)$'

        def command(self,  bot, comm, groups):
            to_parse = groups[0]
            try:
                factoid_dict = learn_grammar(to_parse).parse()
            except ParseError as e:
                bot.reply(comm, 'Parse error: "{}". Trail: {}.'
                                .format(dict(e.error)['message'], e.trail))
            else:
                # bot.reply(comm, 'Yeah! {}'.format(factoid_dict))
                self.plugin.add_factoid(factoid_dict)
                bot.reply(comm, '{user}: Got it.'.format(**comm))

        # Maybe something like: hamper
        # !learn trigger=/^foo$/ response=bar probability=0.5 action=say
        # !learn trigger=/!fire (.*)/ resp="fires $1" prob=1 action=me


class NotRegex(object):
    def __init__(self, string, type):
        self.string = string
        self.type = type

    def match(self, target):
        if self.type == 'is':
            return target == self.string
        elif self.type == 'triggers':
            return target in self.string
        else:
            return False


class RawField(SQLAlchemyBase):
    """New style factoids."""

    __tablename__ = 'raw'

    id = Column(Integer, primary_key=True)
    kind = Column(String)
    data = Column(String)

    def __init__(self, kind, data):
        self.kind = kind
        self.data = data


class OldFactoid(SQLAlchemyBase):
    """The object that will get persisted by the database."""

    __tablename__ = 'factoids'

    id = Column(Integer, primary_key=True)
    type = Column(String)
    trigger = Column(String)
    action = Column(String)
    response = Column(String)

    def __init__(self, trigger, type, action, response):
        self.type = type
        self.trigger = trigger
        self.action = action
        self.response = response


factoids = Factoids()
