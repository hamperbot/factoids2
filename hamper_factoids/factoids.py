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
    priority = 1

    def setup(self, loader):
        super(Factoids, self).setup(loader)
        self.db = loader.db
        SQLAlchemyBase.metadata.create_all(self.db.engine)

        self.factoids = []
        self.load_factoids()
        self.load_old_factoids()

    def load_factoids(self):
        raw_factoids = (self.db.session.query(RawField)
                        .filter(RawField.kind == 'factoid'))

        for raw in raw_factoids:
            factoid = {
                'id': str(raw.id),
                'trigger': None,
                'probability': 1,
                'action': 'say',
                'response': None,
            }
            factoid.update(json.loads(raw.data))
            if factoid['trigger'] and factoid['response']:
                self.factoids.append(self.upgrade_factoid(factoid))

    def load_old_factoids(self):
        for old in self.db.session.query(OldFactoid).all():
            factoid = {
                'id': 'old{}'.format(old.id),
                'trigger': old.trigger,
                'probability': 1,
                'action': old.action,
                'response': old.response,
            }
            self.factoids.append(self.upgrade_factoid(factoid, old.type))

    def upgrade_factoid(self, factoid_dict, type='is'):
        factoid = {
            'trigger': None,
            'action': 'say',
            'response': None,
        }
        factoid.update(factoid_dict)

        match = re.match(r'^/(.*)/(i?)', factoid['trigger'])
        if match:
            kind = 'regex'
            flags = 0
            if 'i' in match.group(2):
                flags |= re.I
            factoid['trigger'] = re.compile(match.group(1), flags)
        else:
            kind = 'full'
            factoid['trigger'] = NotRegex(factoid['trigger'], type)

        if 'probability' not in factoid:
            if kind == 'regex':
                factoid['probability'] = 0.33
            else:
                factoid['probability'] = 1

        return factoid

    def add_factoid(self, factoid_dict, factoid_type='is'):
        """Add an un-upgraded factoid to the db and the in-memory store."""
        factoid = self.upgrade_factoid(factoid_dict, factoid_type)
        self.factoids.append(factoid)
        factoid_orm = RawField('factoid', json.dumps(factoid_dict))
        self.db.session.add(factoid_orm)
        self.db.session.commit()
        factoid['id'] = str(factoid_orm.id)
        return factoid

    def delete_factoid(self, factoid_id):
        factoid_id = str(factoid_id)
        found = None

        for i, factoid in enumerate(self.factoids):
            if factoid['id'] == factoid_id:
                found = i
                break

        if found is not None:
            self.factoids.pop(i)
        else:
            raise IndexError('No such id.')

        if factoid_id.startswith('old'):
            factoid_id = int(factoid_id.strip('old'))
            factoid = (self.db.session.query(OldFactoid)
                        .filter(OldFactoid.id == factoid_id)
                        .first())
        else:
            factoid = (self.db.session.query(RawField)
                       .filter(RawField.id == factoid_id,
                               RawField.kind == 'factoid')
                       .first())

        self.db.session.delete(factoid)
        self.db.session.commit()

    def get_factoid(self, factoid_id):
        factoid_id = str(factoid_id)

        for i, factoid in enumerate(self.factoids):
            if factoid['id'] == factoid_id:
                return factoid

        raise IndexError('No such id.')

    def message(self, bot, comm):
        if super(Factoids, self).message(bot, comm):
            return True

        matched = []
        message = comm['message'].strip()

        for factoid in self.factoids:
            match = factoid['trigger'].search(message)
            if not match and comm['directed']:
                match = factoid['trigger'].search('!' + message)
            if match:
                matched.append((factoid, match))

        if matched:
            # Now choose a factoid, possibly choosing none, based on probabilities
            #
            # Consider n factoids, all of which have probability 1.0. They are
            # mapped onto the space from 0 to n.
            #
            # A random number between 0 and n is generated, and the factoid at
            # that point is chosen.
            #
            #   0         1         2         3
            #   -------------------------------
            #   |   f1    |   f2    |   f3    |
            #                    ^
            #                 if r = 1.7, f2 chosen
            #
            # Now consider n factoids, all of which have probability 0.5.
            #
            #   0         1         2         3
            #   -------------------------------
            #   | f1 | f2 | f3 |   nothing    |
            #                    ^
            #                 if r = 1.7, nothing chosen
            #           ^
            #        if r = 0.7, f2 chosen
            #
            choice = random() * len(matched)
            for factoid, match in matched:
                choice -= factoid['probability']
                if choice < 0:
                    self.send_factoid(bot, comm, factoid, match)
                    return True

    def send_factoid(self, bot, comm, factoid, match):
        tag = 'factoid #{id}'.format(**factoid)

        groups = match.groups()

        if factoid['action'] == 'say':
            bot.reply(comm, factoid['response'], tag=tag,
                      vars=groups, kwvars=factoid)
        elif factoid['action'] == 'reply':
            bot.reply(comm, '{user}: {response}', tag=tag,
                      vars=groups, kwvars=factoid)
        elif factoid['action'] in ['me', 'emote', 'act', 'action']:
            bot.me(comm, factoid['response'], tag=tag,
                   vars=groups, kwvars=factoid)
        else:
            bot.reply(comm, 'Unknown action "{action}" on factoid #{id}',
                      kwvars=factoid, tag='an error on ' + tag)

    # Because this command is defined first, it will be checked first,
    class ClassicLearn(Command):
        """Learn a factoid."""
        name = 'learn'
        regex = r'learn(?:\s+that)?\s+(.+)\s+(\w+)\s+<(\w+)>\s+(.*)'

        def command(self, bot, comm, groups):
            trigger, factoid_type, action, response = groups
            factoid = {
                'trigger': trigger,
                'action': action,
                'response': response,
            }
            factoid = self.plugin.add_factoid(factoid, factoid_type)
            bot.reply(comm, "{user}: Well, ok, but that's the old way. I "
                            "added factoid #{0}."
                            .format(factoid['id'], **comm))
            return True

    class ModernLearn(Command):
        name = 'learn'
        regex = r'^learn\s+(.*=.*)$'
        short_desc = ('!learn key=val key=val - Keys can be response, trigger, '
                      'action, and probability. Values can be word, "string", '
                      'or /regex/')

        valid_keys = ['response', 'trigger', 'action', 'probability']

        def command(self,  bot, comm, groups):
            to_parse = groups[0]
            try:
                factoid_dict = learn_grammar(to_parse).parse()
                for key in factoid_dict:
                    if key not in self.valid_keys:
                        raise ValueError(key)
            except ParseError as e:
                bot.reply(comm, 'Parse error: "{}". Trail: {}.'
                                .format(dict(e.error)['message'], e.trail))
            except ValueError as e:
                bot.reply(comm, "{user}: {} isn't a valid key. The valid keys "
                                "are trigger, response, action, probability."
                                .format(e.message, **comm))
            else:
                factoid = self.plugin.add_factoid(factoid_dict)
                msg = "{user}: Got it. That's factoid #{id}"
                if factoid['probability'] < 1:
                    msg += ' (probability={probability})'

                bot.reply(comm, msg, kwvars={
                        'id': factoid['id'],
                        'probability': factoid['probability']
                    })

    def factoid_query(self, bot, to_parse):
        try:
            parsed = learn_grammar(to_parse).parse()
            if parsed.keys() != ['id']:
                bot.reply(comm, ('{user}: I only know how to find by id '
                                 'right now.'))
        except ParseError as e:
            bot.reply(comm, 'Parse error: "{}". Trail: {}.'
                            .format(dict(e.error)['message'], e.trail))
            return None
        else:
            return self.get_factoid(parsed['id'])

    class Unlearn(Command):
        name = 'unlearn'
        regex = r'^unlearn\s+(.*=.*)$'
        short_desc = ('!unlearn id=num - '
                      'Delete a factoid by id (like !unlearn id=4)')

        def command(self, bot, comm, groups):
            to_parse = groups[0]
            try:
                to_delete = self.plugin.factoid_query(bot, to_parse)
                self.plugin.delete_factoid(to_delete['id'])
                bot.reply(comm, '{user}: Ok.')
            except IndexError:
                bot.reply(comm, "{user}: I couldn't find that.")

    class Dump(Command):
        name = 'dumpfactoid'
        regex = '^dump\s*factoid\s+(.*=.*)$'
        short_desc = ('!dumpfactoid id=num - '
                      'Dump all information about a factoid by id')

        def factoid_string(self, factoid):
            trigger = factoid['trigger']
            if isinstance(trigger, NotRegex):
                if trigger.type == 'is':
                    trigger_rep = '"{}"'.format(trigger.string)
                elif trigger.type == 'triggers':
                    trigger_rep = '/{}/'.format(trigger.string)
                else:
                    trigger_rep = str(trigger)
            else:  # assume regex
                trigger_rep = '/{}/'.format(trigger.pattern)

            return (
                'id={id} '
                'trigger={trigger} '
                'response="{response}" '
                'action={action} '
                'probability={probability}'
            ).format(
                id=factoid['id'],
                trigger=trigger_rep,
                response=factoid['response'],
                action=factoid['action'],
                probability=factoid['probability'],
            ).replace('{', '{{').replace('}', '}}')

        def command(self, bot, comm, groups):
            to_parse = groups[0]
            try:
                factoid = self.plugin.factoid_query(bot, to_parse)
                factoid_rep = self.factoid_string(factoid)
                bot.reply(comm, '{user}: {}', vars=[factoid_rep])
            except IndexError:
                bot.reply(comm, "{user}: I couldn't find that.")


class NotRegex(object):
    def __init__(self, string, type):
        self.string = string
        self.type = type

    def search(self, target):
        if self.type == 'is':
            if target == self.string:
                return self.FakeMatch()
        elif self.type == 'triggers':
            if self.string in target:
                return self.FakeMatch()

        return None

    def __repr__(self):
        return ('<{} {} "{}">'
                .format(self.__class__.__name__, self.type, self.string))

    class FakeMatch(object):
        def groups(self):
            return []


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
