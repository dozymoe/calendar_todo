#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
import uuid
import vobject
import dateutil.tz
import pytz
import datetime
import xml.dom.minidom
from trytond.model import ModelSQL, ModelView, fields
from trytond.tools import reduce_ids
from trytond.backend import TableHandler
from trytond.pyson import Eval, If, Bool
from trytond.transaction import Transaction
from trytond.pool import Pool

tzlocal = dateutil.tz.tzlocal()
tzutc = dateutil.tz.tzutc()

domimpl = xml.dom.minidom.getDOMImplementation()


class Todo(ModelSQL, ModelView):
    "Todo"
    _description = __doc__
    _name = 'calendar.todo'
    _rec_name = 'uuid'

    calendar = fields.Many2One('calendar.calendar', 'Calendar',
            required=True, select=True, ondelete="CASCADE")
    alarms = fields.One2Many('calendar.todo.alarm', 'todo', 'Alarms')
    classification = fields.Selection([
        ('public', 'Public'),
        ('private', 'Private'),
        ('confidential', 'Confidential'),
        ], 'Classification', required=True)
    completed = fields.DateTime('Completed',
        states={
            'readonly': Eval('status') != 'completed',
            }, depends=['status'])
    description = fields.Text('Description')
    dtstart = fields.DateTime('Start Date', select=True)
    location = fields.Many2One('calendar.location', 'Location')
    organizer = fields.Char('Organizer', states={
            'required': If(Bool(Eval('attendees')),
                ~Eval('parent'), False),
            }, depends=['attendees', 'parent'])
    attendees = fields.One2Many('calendar.todo.attendee', 'todo',
            'Attendees')
    percent_complete = fields.Integer('Percent complete', required=True,
        states={
            'readonly': ~Eval('status').in_(['needs-action', 'in-process']),
            }, depends=['status'])
    occurences = fields.One2Many('calendar.todo', 'parent', 'Occurences',
            domain=[
                ('uuid', '=', Eval('uuid')),
                ('calendar', '=', Eval('calendar')),
            ],
            states={
                'invisible': Bool(Eval('parent')),
            }, depends=['uuid', 'calendar', 'parent'])
    recurrence = fields.DateTime('Recurrence', select=True, states={
            'invisible': ~Eval('_parent_parent'),
            'required': Bool(Eval('_parent_parent')),
            }, depends=['parent'])
    sequence = fields.Integer('Sequence', required=True)
    parent = fields.Many2One('calendar.todo', 'Parent',
            domain=[
                ('uuid', '=', Eval('uuid')),
                ('parent', '=', None),
                ('calendar', '=', Eval('calendar'))
            ],
            ondelete='CASCADE', depends=['uuid', 'calendar'])
    timezone = fields.Selection('timezones', 'Timezone')
    status = fields.Selection([
        ('', ''),
        ('needs-action', 'Needs-Action'),
        ('completed', 'Completed'),
        ('in-process', 'In-Process'),
        ('cancelled', 'Cancelled'),
        ], 'Status', on_change=['status', 'completed', 'percent_complete'])
    summary = fields.Char('Summary')
    uuid = fields.Char('UUID', required=True,
            help='Universally Unique Identifier', select=True)
    due = fields.DateTime('Due Date', select=True)
    categories = fields.Many2Many('calendar.todo-calendar.category',
            'todo', 'category', 'Categories')
    exdates = fields.One2Many('calendar.todo.exdate', 'todo',
        'Exception Dates',
        states={
            'invisible': Bool(Eval('parent')),
            }, depends=['parent'])
    exrules = fields.One2Many('calendar.todo.exrule', 'todo',
        'Exception Rules',
        states={
            'invisible': Bool(Eval('parent')),
            }, depends=['parent'])
    rdates = fields.One2Many('calendar.todo.rdate', 'todo', 'Recurrence Dates',
            states={
                'invisible': Bool(Eval('parent')),
            }, depends=['parent'])
    rrules = fields.One2Many('calendar.todo.rrule', 'todo', 'Recurrence Rules',
            states={
                'invisible': Bool(Eval('parent')),
            }, depends=['parent'])
    calendar_owner = fields.Function(fields.Many2One('res.user', 'Owner'),
            'get_calendar_field', searcher='search_calendar_field')
    calendar_read_users = fields.Function(fields.One2Many('res.user', None,
        'Read Users'), 'get_calendar_field', searcher='search_calendar_field')
    calendar_write_users = fields.Function(fields.One2Many('res.user', None,
        'Write Users'), 'get_calendar_field', searcher='search_calendar_field')
    vtodo = fields.Binary('vtodo')

    def __init__(self):
        super(Todo, self).__init__()
        self._sql_constraints = [
            #XXX should be unique across all componenets
            ('uuid_recurrence_uniq', 'UNIQUE(uuid, calendar, recurrence)',
                'UUID and recurrence must be unique in a calendar!'),
        ]
        self._constraints += [
            ('check_recurrence', 'invalid_recurrence'),
        ]
        self._error_messages.update({
            'invalid_recurrence': 'Recurrence can not be recurrent!',
        })

    def init(self, module_name):
        # Migrate from 1.4: remove classification_public
        model_data_obj = Pool().get('ir.model.data')
        rule_obj = Pool().get('ir.rule')
        with Transaction().set_user(0):
            model_data_ids = model_data_obj.search([
                ('fs_id', '=', 'rule_group_read_todo_line3'),
                ('module', '=', module_name),
                ('inherit', '=', None),
                ], limit=1)
            if model_data_ids:
                model_data = model_data_obj.browse(model_data_ids[0])
                rule_obj.delete(model_data.db_id)
        return super(Todo, self).init(module_name)

    def default_uuid(self):
        return str(uuid.uuid4())

    def default_sequence(self):
        return 0

    def default_classification(self):
        return 'public'

    def default_timezone(self):
        user_obj = Pool().get('res.user')
        user = user_obj.browse(Transaction().user)
        return user.timezone

    def default_percent_complete(self):
        return 0

    def on_change_status(self, vals):
        res = {}
        if 'status' not in vals:
            return res
        if vals['status'] == 'completed':
            res['percent_complete'] = 100
            if not vals.get('completed'):
                res['completed'] = datetime.datetime.now()

        return res

    def timezones(self):
        return [(x, x) for x in pytz.common_timezones] + [('', '')]

    def get_calendar_field(self, ids, name):
        assert name in ('calendar_owner', 'calendar_read_users',
                'calendar_write_users'), 'Invalid name'
        res = {}
        for todo in self.browse(ids):
            name = name[9:]
            if name in ('read_users', 'write_users'):
                res[todo.id] = [x.id for x in todo.calendar[name]]
            else:
                res[todo.id] = todo.calendar[name].id
        return res

    def search_calendar_field(self, name, clause):
        return [('calendar.' + name[9:],) + clause[1:]]

    def check_recurrence(self, ids):
        '''
        Check the recurrence is not recurrent.
        '''
        for todo in self.browse(ids):
            if not todo.parent:
                continue
            if todo.rdates \
                    or todo.rrules \
                    or todo.exdates \
                    or todo.exrules \
                    or todo.occurences:
                return False
        return True

    def create(self, values):
        calendar_obj = Pool().get('calendar.calendar')
        collection_obj = Pool().get('webdav.collection')

        res = super(Todo, self).create(values)
        todo = self.browse(res)
        if (todo.calendar.owner
                and (todo.organizer == todo.calendar.owner.email
                    or (todo.parent
                        and todo.parent.organizer == \
                            todo.parent.calendar.owner.email))):
            if todo.organizer == todo.calendar.owner.email:
                attendee_emails = [x.email for x in todo.attendees
                        if x.status != 'declined'
                        and x.email != todo.organizer]
            else:
                attendee_emails = [x.email for x in todo.parent.attendees
                        if x.status != 'declined'
                        and x.email != todo.parent.organizer]
            if attendee_emails:
                with Transaction().set_user(0):
                    calendar_ids = calendar_obj.search([
                        ('owner.email', 'in', attendee_emails),
                        ])
                    if not todo.recurrence:
                        for calendar_id in calendar_ids:
                            new_id = self.copy(todo.id, default={
                                'calendar': calendar_id,
                                'occurences': None,
                                })
                            for occurence in todo.occurences:
                                self.copy(occurence.id, default={
                                    'calendar': calendar_id,
                                    'parent': new_id,
                                    })
                    else:
                        parent_ids = self.search([
                            ('uuid', '=', todo.uuid),
                            ('calendar.owner.email', 'in', attendee_emails),
                            ('id', '!=', todo.id),
                            ('recurrence', '=', None),
                            ])
                        for parent in self.browse(parent_ids):
                            self.copy(todo.id, default={
                                'calendar': parent.calendar.id,
                                'parent': parent.id,
                                })
        # Restart the cache for todo
        collection_obj.todo.reset()
        return res

    def _todo2update(self, todo):
        pool = Pool()
        rdate_obj = pool.get('calendar.todo.rdate')
        exdate_obj = pool.get('calendar.todo.exdate')
        rrule_obj = pool.get('calendar.todo.rrule')
        exrule_obj = pool.get('calendar.todo.exrule')

        res = {}
        res['summary'] = todo.summary
        res['description'] = todo.description
        res['dtstart'] = todo.dtstart
        res['percent_complete'] = todo.percent_complete
        res['completed'] = todo.completed
        res['location'] = todo.location.id
        res['status'] = todo.status
        res['organizer'] = todo.organizer
        res['rdates'] = [('delete_all',)]
        for rdate in todo.rdates:
            vals = rdate_obj._date2update(rdate)
            res['rdates'].append(('create', vals))
        res['exdates'] = [('delete_all',)]
        for exdate in todo.exdates:
            vals = exdate_obj._date2update(exdate)
            res['exdates'].append(('create', vals))
        res['rrules'] = [('delete_all',)]
        for rrule in todo.rrules:
            vals = rrule_obj._rule2update(rrule)
            res['rrules'].append(('create', vals))
        res['exrules'] = [('delete_all',)]
        for exrule in todo.exrules:
            vals = exrule_obj._rule2update(exrule)
            res['exrules'].append(('create', vals))
        return res

    def write(self, ids, values):
        calendar_obj = Pool().get('calendar.calendar')
        collection_obj = Pool().get('webdav.collection')

        cursor = Transaction().cursor

        values = values.copy()
        if 'sequence' in values:
            del values['sequence']

        res = super(Todo, self).write(ids, values)

        if isinstance(ids, (int, long)):
            ids = [ids]

        for i in range(0, len(ids), cursor.IN_MAX):
            sub_ids = ids[i:i + cursor.IN_MAX]
            red_sql, red_ids = reduce_ids('id', sub_ids)
            cursor.execute('UPDATE "' + self._table + '" ' \
                    'SET sequence = sequence + 1 ' \
                    'WHERE ' + red_sql, red_ids)

        for todo in self.browse(ids):
            if todo.calendar.owner \
                    and (todo.organizer == todo.calendar.owner.email \
                    or (todo.parent \
                    and todo.parent.organizer == todo.calendar.owner.email)):
                if todo.organizer == todo.calendar.owner.email:
                    attendee_emails = [x.email for x in todo.attendees
                            if x.status != 'declined'
                            and x.email != todo.organizer]
                else:
                    attendee_emails = [x.email for x in todo.parent.attendees
                            if x.status != 'declined'
                            and x.email != todo.parent.organizer]
                if attendee_emails:
                    with Transaction().set_user(0):
                        todo_ids = self.search([
                            ('uuid', '=', todo.uuid),
                            ('calendar.owner.email', 'in', attendee_emails),
                            ('id', '!=', todo.id),
                            ('recurrence', '=', todo.recurrence),
                            ])
                    for todo2 in self.browse(todo_ids):
                        if todo2.calendar.owner.email in attendee_emails:
                            attendee_emails.remove(todo2.calendar.owner.email)
                    with Transaction().set_user(0):
                        self.write(todo_ids, self._todo2update(todo))
                if attendee_emails:
                    with Transaction().set_user(0):
                        calendar_ids = calendar_obj.search([
                            ('owner.email', 'in', attendee_emails),
                            ])
                        if not todo.recurrence:
                            for calendar_id in calendar_ids:
                                new_id = self.copy(todo.id, default={
                                    'calendar': calendar_id,
                                    'occurences': None,
                                    })
                                for occurence in todo.occurences:
                                    self.copy(occurence.id, default={
                                        'calendar': calendar_id,
                                        'parent': new_id,
                                        })
                        else:
                            parent_ids = self.search([
                                    ('uuid', '=', todo.uuid),
                                    ('calendar.owner.email', 'in',
                                        attendee_emails),
                                    ('id', '!=', todo.id),
                                    ('recurrence', '=', None),
                                    ])
                            for parent in self.browse(parent_ids):
                                self.copy(todo.id, default={
                                    'calendar': parent.calendar.id,
                                    'parent': parent.id,
                                    })
        # Restart the cache for todo
        collection_obj.todo.reset()
        return res

    def delete(self, ids):
        attendee_obj = Pool().get('calendar.todo.attendee')
        collection_obj = Pool().get('webdav.collection')

        if isinstance(ids, (int, long)):
            ids = [ids]
        for todo in self.browse(ids):
            if todo.calendar.owner \
                    and (todo.organizer == todo.calendar.owner.email \
                    or (todo.parent \
                    and todo.parent.organizer == todo.calendar.owner.email)):
                if todo.organizer == todo.calendar.owner.email:
                    attendee_emails = [x.email for x in todo.attendees
                            if x.email != todo.organizer]
                else:
                    attendee_emails = [x.email for x in todo.parent.attendees
                            if x.email != todo.parent.organizer]
                if attendee_emails:
                    with Transaction().set_user(0):
                        todo_ids = self.search([
                            ('uuid', '=', todo.uuid),
                            ('calendar.owner.email', 'in', attendee_emails),
                            ('id', '!=', todo.id),
                            ('recurrence', '=', todo.recurrence),
                            ])
                        self.delete(todo_ids)
            elif todo.organizer \
                    or (todo.parent and todo.parent.organizer):
                if todo.organizer:
                    organizer = todo.organizer
                else:
                    organizer = todo.parent.organizer
                with Transaction().set_user(0):
                    todo_ids = self.search([
                        ('uuid', '=', todo.uuid),
                        ('calendar.owner.email', '=', organizer),
                        ('id', '!=', todo.id),
                        ('recurrence', '=', todo.recurrence),
                        ], limit=1)
                    if todo_ids:
                        todo2 = self.browse(todo_ids[0])
                        for attendee in todo2.attendees:
                            if attendee.email == todo.calendar.owner.email:
                                attendee_obj.write(attendee.id, {
                                    'status': 'declined',
                                    })
        res = super(Todo, self).delete(ids)
        # Restart the cache for todo
        collection_obj.todo.reset()
        return res

    def ical2values(self, todo_id, ical, calendar_id, vtodo=None):
        '''
        Convert iCalendar to values for create or write

        :param todo_id: the todo id for write or None for create
        :param ical: a ical instance of vobject
        :param calendar_id: the calendar id of the todo
        :param vtodo: the vtodo of the ical to use if None use the first one
        :return: a dictionary with values
        '''
        pool = Pool()
        category_obj = pool.get('calendar.category')
        location_obj = pool.get('calendar.location')
        alarm_obj = pool.get('calendar.todo.alarm')
        attendee_obj = pool.get('calendar.todo.attendee')
        rdate_obj = pool.get('calendar.todo.rdate')
        exdate_obj = pool.get('calendar.todo.exdate')
        rrule_obj = pool.get('calendar.todo.rrule')
        exrule_obj = pool.get('calendar.todo.exrule')

        vtodos = []
        if not vtodo:
            vtodo = ical.vtodo

            for i in ical.getChildren():
                if i.name == 'VTODO' \
                        and i != vtodo:
                    vtodos.append(i)

        todo = None
        if todo_id:
            todo = self.browse(todo_id)
        res = {}
        if not todo:
            if hasattr(vtodo, 'uid'):
                res['uuid'] = vtodo.uid.value
            else:
                res['uuid'] = str(uuid.uuid4())
        if hasattr(vtodo, 'summary'):
            res['summary'] = vtodo.summary.value
        else:
            res['summary'] = None
        if hasattr(vtodo, 'description'):
            res['description'] = vtodo.description.value
        else:
            res['description'] = None
        if hasattr(vtodo, 'percent_complete'):
            res['percent_complete'] = int(vtodo.percent_complete.value)
        else:
            res['percent_complete'] = None

        if hasattr(vtodo, 'completed'):
            if not isinstance(vtodo.completed.value, datetime.datetime):
                res['completed'] = datetime.datetime.combine(
                    vtodo.completed.value, datetime.time())
            else:
                if vtodo.completed.value.tzinfo:
                    res['completed'] = vtodo.completed.value.astimezone(
                        tzlocal)
                else:
                    res['completed'] = vtodo.completed.value

        if hasattr(vtodo, 'dtstart'):
            if not isinstance(vtodo.dtstart.value, datetime.datetime):
                res['dtstart'] = datetime.datetime.combine(vtodo.dtstart.value,
                        datetime.time())
            else:
                if vtodo.dtstart.value.tzinfo:
                    res['dtstart'] = vtodo.dtstart.value.astimezone(tzlocal)
                else:
                    res['dtstart'] = vtodo.dtstart.value

        if hasattr(vtodo, 'due'):
            if not isinstance(vtodo.due.value, datetime.datetime):
                res['due'] = datetime.datetime.combine(vtodo.due.value,
                        datetime.time())
            else:
                if vtodo.due.value.tzinfo:
                    res['due'] = vtodo.due.value.astimezone(tzlocal)
                else:
                    res['due'] = vtodo.due.value

        if hasattr(vtodo, 'recurrence-id'):
            if not isinstance(vtodo.recurrence_id.value, datetime.datetime):
                res['recurrence'] = datetime.datetime.combine(
                        vtodo.recurrence_id.value, datetime.time())
            else:
                if vtodo.recurrence_id.value.tzinfo:
                    res['recurrence'] = \
                            vtodo.recurrence_id.value.astimezone(tzlocal)
                else:
                    res['recurrence'] = vtodo.recurrence_id.value
        else:
            res['recurrence'] = None
        if hasattr(vtodo, 'status'):
            res['status'] = vtodo.status.value.lower()
        else:
            res['status'] = ''
        if hasattr(vtodo, 'categories'):
            category_ids = category_obj.search([
                ('name', 'in', [x for x in vtodo.categories.value]),
                ])
            categories = category_obj.browse(category_ids)
            category_names2ids = {}
            for category in categories:
                category_names2ids[category.name] = category.id
            for category in vtodo.categories.value:
                if category not in category_names2ids:
                    category_ids.append(category_obj.create({
                        'name': category,
                        }))
            res['categories'] = [('set', category_ids)]
        else:
            res['categories'] = [('unlink_all',)]
        if hasattr(vtodo, 'class'):
            if getattr(vtodo, 'class').value.lower() in \
                    dict(self.classification.selection):
                res['classification'] = getattr(vtodo, 'class').value.lower()
            else:
                res['classification'] = 'public'
        else:
            res['classification'] = 'public'
        if hasattr(vtodo, 'location'):
            location_ids = location_obj.search([
                ('name', '=', vtodo.location.value),
                ], limit=1)
            if not location_ids:
                location_id = location_obj.create({
                    'name': vtodo.location.value,
                    })
            else:
                location_id = location_ids[0]
            res['location'] = location_id
        else:
            res['location'] = None

        res['calendar'] = calendar_id

        if hasattr(vtodo, 'organizer'):
            if vtodo.organizer.value.lower().startswith('mailto:'):
                res['organizer'] = vtodo.organizer.value[7:]
            else:
                res['organizer'] = vtodo.organizer.value
        else:
            res['organizer'] = None

        attendees_todel = {}
        if todo:
            for attendee in todo.attendees:
                attendees_todel[attendee.email] = attendee.id
        res['attendees'] = []
        if hasattr(vtodo, 'attendee'):
            while vtodo.attendee_list:
                attendee = vtodo.attendee_list.pop()
                vals = attendee_obj.attendee2values(attendee)
                if vals['email'] in attendees_todel:
                    res['attendees'].append(('write',
                        attendees_todel[vals['email']], vals))
                    del attendees_todel[vals['email']]
                else:
                    res['attendees'].append(('create', vals))
        res['attendees'].append(('delete', attendees_todel.values()))

        res['rdates'] = []
        if todo:
            res['rdates'].append(('delete', [x.id for x in todo.rdates]))
        if hasattr(vtodo, 'rdate'):
            while vtodo.rdate_list:
                rdate = vtodo.rdate_list.pop()
                for date in rdate.value:
                    vals = rdate_obj.date2values(date)
                    res['rdates'].append(('create', vals))

        res['exdates'] = []
        if todo:
            res['exdates'].append(('delete', [x.id for x in todo.exdates]))
        if hasattr(vtodo, 'exdate'):
            while vtodo.exdate_list:
                exdate = vtodo.exdate_list.pop()
                for date in exdate.value:
                    vals = exdate_obj.date2values(date)
                    res['exdates'].append(('create', vals))

        res['rrules'] = []
        if todo:
            res['rrules'].append(('delete', [x.id for x in todo.rrules]))
        if hasattr(vtodo, 'rrule'):
            while vtodo.rrule_list:
                rrule = vtodo.rrule_list.pop()
                vals = rrule_obj.rule2values(rrule)
                res['rrules'].append(('create', vals))

        res['exrules'] = []
        if todo:
            res['exrules'].append(('delete', [x.id for x in todo.exrules]))
        if hasattr(vtodo, 'exrule'):
            while vtodo.exrule_list:
                exrule = vtodo.exrule_list.pop()
                vals = exrule_obj.rule2values(exrule)
                res['exrules'].append(('create', vals))

        if todo:
            res.setdefault('alarms', [])
            res['alarms'].append(('delete', [x.id for x in todo.alarms]))
        if hasattr(vtodo, 'valarm'):
            res.setdefault('alarms', [])
            while vtodo.valarm_list:
                valarm = vtodo.valarm_list.pop()
                vals = alarm_obj.valarm2values(valarm)
                res['alarms'].append(('create', vals))

        if hasattr(ical, 'vtimezone'):
            if ical.vtimezone.tzid.value in pytz.common_timezones:
                res['timezone'] = ical.vtimezone.tzid.value
            else:
                for timezone in pytz.common_timezones:
                    if ical.vtimezone.tzid.value.endswith(timezone):
                        res['timezone'] = timezone

        res['vtodo'] = vtodo.serialize()

        occurences_todel = []
        if todo:
            occurences_todel = [x.id for x in todo.occurences]
        for vtodo in vtodos:
            todo_id = None
            if todo:
                for occurence in todo.occurences:
                    if occurence.recurrence.replace(tzinfo=tzlocal) \
                            == vtodo.recurrence_id.value:
                        todo_id = occurence.id
                        occurences_todel.remove(occurence.id)
            vals = self.ical2values(todo_id, ical, calendar_id, vtodo=vtodo)
            if todo:
                vals['uuid'] = todo.uuid
            else:
                vals['uuid'] = res['uuid']
            res.setdefault('occurences', [])
            if todo_id:
                res['occurences'].append(('write', todo_id, vals))
            else:
                res['occurences'].append(('create', vals))
        if occurences_todel:
            res.setdefault('occurences', [])
            res['occurences'].append(('delete', occurences_todel))
        return res

    def todo2ical(self, todo):
        '''
        Return an iCalendar instance of vobject for todo

        :param todo: a BrowseRecord of calendar.todo
            or a calendar.todo id
        :return: an iCalendar instance of vobject
        '''
        pool = Pool()
        user_obj = pool.get('res.user')
        alarm_obj = pool.get('calendar.todo.alarm')
        attendee_obj = pool.get('calendar.todo.attendee')
        rdate_obj = pool.get('calendar.todo.rdate')
        exdate_obj = pool.get('calendar.todo.exdate')
        rrule_obj = pool.get('calendar.todo.rrule')
        exrule_obj = pool.get('calendar.todo.exrule')

        if isinstance(todo, (int, long)):
            todo = self.browse(todo)

        user = user_obj.browse(Transaction().user)
        if todo.timezone:
            tztodo = pytz.timezone(todo.timezone)
        elif user.timezone:
                tztodo = pytz.timezone(user.timezone)
        else:
            tztodo = tzlocal

        ical = vobject.iCalendar()
        vtodo = ical.add('vtodo')
        if todo.vtodo:
            ical.vtodo = vobject.readOne(todo.vtodo)
            vtodo = ical.vtodo
            ical.vtodo.transformToNative()
        if todo.summary:
            if not hasattr(vtodo, 'summary'):
                vtodo.add('summary')
            vtodo.summary.value = todo.summary
        elif hasattr(vtodo, 'summary'):
            del vtodo.summary
        if todo.percent_complete:
            if not hasattr(vtodo, 'percent-complete'):
                vtodo.add('percent-complete')
            vtodo.percent_complete.value = str(todo.percent_complete)
        elif hasattr(vtodo, 'percent_complete'):
            del vtodo.percent_complete
        if todo.description:
            if not hasattr(vtodo, 'description'):
                vtodo.add('description')
            vtodo.description.value = todo.description
        elif hasattr(vtodo, 'description'):
            del vtodo.description

        if todo.completed:
            if not hasattr(vtodo, 'completed'):
                vtodo.add('completed')
            vtodo.completed.value = todo.completed.replace(tzinfo=tzlocal)\
                    .astimezone(tzutc)
        elif hasattr(vtodo, 'completed'):
            del vtodo.completed

        if todo.dtstart:
            if not hasattr(vtodo, 'dtstart'):
                vtodo.add('dtstart')
            vtodo.dtstart.value = todo.dtstart.replace(tzinfo=tzlocal)\
                    .astimezone(tztodo)
        elif hasattr(vtodo, 'dtstart'):
            del vtodo.dtstart

        if todo.due:
            if not hasattr(vtodo, 'due'):
                vtodo.add('due')
            vtodo.due.value = todo.due.replace(tzinfo=tzlocal)\
                    .astimezone(tztodo)
        elif hasattr(vtodo, 'due'):
            del vtodo.due

        if not hasattr(vtodo, 'created'):
            vtodo.add('created')
        vtodo.created.value = todo.create_date.replace(
            tzinfo=tzlocal).astimezone(tztodo)
        if not hasattr(vtodo, 'dtstamp'):
            vtodo.add('dtstamp')
        date = todo.write_date or todo.create_date
        vtodo.dtstamp.value = date.replace(tzinfo=tzlocal).astimezone(tztodo)
        if not hasattr(vtodo, 'last-modified'):
            vtodo.add('last-modified')
        vtodo.last_modified.value = date.replace(
            tzinfo=tzlocal).astimezone(tztodo)
        if todo.recurrence and todo.parent:
            if not hasattr(vtodo, 'recurrence-id'):
                vtodo.add('recurrence-id')
            vtodo.recurrence_id.value = todo.recurrence\
                    .replace(tzinfo=tzlocal).astimezone(tztodo)
        elif hasattr(vtodo, 'recurrence-id'):
            del vtodo.recurrence_id
        if todo.status:
            if not hasattr(vtodo, 'status'):
                vtodo.add('status')
            vtodo.status.value = todo.status.upper()
        elif hasattr(vtodo, 'status'):
            del vtodo.status
        if not hasattr(vtodo, 'uid'):
            vtodo.add('uid')
        vtodo.uid.value = todo.uuid
        if not hasattr(vtodo, 'sequence'):
            vtodo.add('sequence')
        vtodo.sequence.value = str(todo.sequence) or '0'
        if todo.categories:
            if not hasattr(vtodo, 'categories'):
                vtodo.add('categories')
            vtodo.categories.value = [x.name for x in todo.categories]
        elif hasattr(vtodo, 'categories'):
            del vtodo.categories
        if not hasattr(vtodo, 'class'):
            vtodo.add('class')
            getattr(vtodo, 'class').value = todo.classification.upper()
        elif getattr(vtodo, 'class').value.lower() in \
                dict(self.classification.selection):
            getattr(vtodo, 'class').value = todo.classification.upper()
        if todo.location:
            if not hasattr(vtodo, 'location'):
                vtodo.add('location')
            vtodo.location.value = todo.location.name
        elif hasattr(vtodo, 'location'):
            del vtodo.location

        if todo.organizer:
            if not hasattr(vtodo, 'organizer'):
                vtodo.add('organizer')
            vtodo.organizer.value = 'MAILTO:' + todo.organizer
        elif hasattr(vtodo, 'organizer'):
            del vtodo.organizer

        vtodo.attendee_list = []
        for attendee in todo.attendees:
            vtodo.attendee_list.append(
                attendee_obj.attendee2attendee(attendee))

        if todo.rdates:
            vtodo.add('rdate')
            vtodo.rdate.value = []
            for rdate in todo.rdates:
                vtodo.rdate.value.append(rdate_obj.date2date(rdate))

        if todo.exdates:
            vtodo.add('exdate')
            vtodo.exdate.value = []
            for exdate in todo.exdates:
                vtodo.exdate.value.append(exdate_obj.date2date(exdate))

        if todo.rrules:
            for rrule in todo.rrules:
                vtodo.add('rrule').value = rrule_obj.rule2rule(rrule)

        if todo.exrules:
            for exrule in todo.exrules:
                vtodo.add('exrule').value = exrule_obj.rule2rule(exrule)

        vtodo.valarm_list = []
        for alarm in todo.alarms:
            valarm = alarm_obj.alarm2valarm(alarm)
            if valarm:
                vtodo.valarm_list.append(valarm)

        for occurence in todo.occurences:
            rical = self.todo2ical(occurence)
            ical.vtodo_list.append(rical.vtodo)
        return ical

Todo()


class TodoCategory(ModelSQL):
    'Todo - Category'
    _description = __doc__
    _name = 'calendar.todo-calendar.category'

    todo = fields.Many2One('calendar.todo', 'To-Do', ondelete='CASCADE',
            required=True, select=True)
    category = fields.Many2One('calendar.category', 'Category',
            ondelete='CASCADE', required=True, select=True)

TodoCategory()


class TodoRDate(ModelSQL, ModelView):
    'Todo Recurrence Date'
    _description = __doc__
    _name = 'calendar.todo.rdate'
    _inherits = {'calendar.date': 'calendar_date'}
    _rec_name = 'datetime'

    calendar_date = fields.Many2One('calendar.date', 'Calendar Date',
            required=True, ondelete='CASCADE', select=True)
    todo = fields.Many2One('calendar.todo', 'Todo', ondelete='CASCADE',
            select=True, required=True)

    def init(self, module_name):
        cursor = Transaction().cursor
        # Migration from 1.4: calendar_rdate renamed to calendar_date
        table = TableHandler(cursor, self, module_name)
        old_column = 'calendar_rdate'
        if table.column_exist(old_column):
            table.column_rename(old_column, 'calendar_date')

        return super(TodoRDate, self).init(module_name)

    def create(self, values):
        todo_obj = Pool().get('calendar.todo')
        if values.get('todo'):
            # Update write_date of todo
            todo_obj.write(values['todo'], {})
        return super(TodoRDate, self).create(values)

    def write(self, ids, values):
        todo_obj = Pool().get('calendar.todo')
        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_ids = [x.todo.id for x in self.browse(ids)]
        if values.get('todo'):
            todo_ids.append(values['todo'])
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})
        return super(TodoRDate, self).write(ids, values)

    def delete(self, ids):
        todo_obj = Pool().get('calendar.todo')
        rdate_obj = Pool().get('calendar.date')
        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_rdates = self.browse(ids)
        rdate_ids = [a.calendar_date.id for a in todo_rdates]
        todo_ids = [x.todo.id for x in todo_rdates]
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})
        res = super(TodoRDate, self).delete(ids)
        if rdate_ids:
            rdate_obj.delete(rdate_ids)
        return res

    def _date2update(self, date):
        date_obj = Pool().get('calendar.date')
        return date_obj._date2update(date)

    def date2values(self, date):
        date_obj = Pool().get('calendar.date')
        return date_obj.date2values(date)

    def date2date(self, date):
        date_obj = Pool().get('calendar.date')
        return date_obj.date2date(date)

TodoRDate()


class TodoRRule(ModelSQL, ModelView):
    'Recurrence Rule'
    _description = __doc__
    _name = 'calendar.todo.rrule'
    _inherits = {'calendar.rrule': 'calendar_rrule'}
    _rec_name = 'freq'

    calendar_rrule = fields.Many2One('calendar.rrule', 'Calendar RRule',
            required=True, ondelete='CASCADE', select=True)
    todo = fields.Many2One('calendar.todo', 'Todo', ondelete='CASCADE',
            select=True, required=True)

    def create(self, values):
        todo_obj = Pool().get('calendar.todo')
        if values.get('todo'):
            # Update write_date of todo
            todo_obj.write(values['todo'], {})
        return super(TodoRRule, self).create(values)

    def write(self, ids, values):
        todo_obj = Pool().get('calendar.todo')
        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_ids = [x.todo.id for x in self.browse(ids)]
        if values.get('todo'):
            todo_ids.append(values['todo'])
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})
        return super(TodoRRule, self).write(ids, values)

    def delete(self, ids):
        todo_obj = Pool().get('calendar.todo')
        rrule_obj = Pool().get('calendar.rrule')
        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_rrules = self.browse(ids)
        rrule_ids = [a.calendar_rrule.id for a in todo_rrules]
        todo_ids = [x.todo.id for x in todo_rrules]
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})
        res = super(TodoRRule, self).delete(ids)
        if rrule_ids:
            rrule_obj.delete(rrule_ids)
        return res

    def _rule2update(self, rule):
        rule_obj = Pool().get('calendar.rrule')
        return rule_obj._rule2update(rule)

    def rule2values(self, rule):
        rule_obj = Pool().get('calendar.rrule')
        return rule_obj.rule2values(rule)

    def rule2rule(self, rule):
        rule_obj = Pool().get('calendar.rrule')
        return rule_obj.rule2rule(rule)

TodoRRule()


class TodoExDate(TodoRDate):
    'Exception Date'
    _description = __doc__
    _name = 'calendar.todo.exdate'

TodoExDate()


class TodoExRule(TodoRRule):
    'Exception Rule'
    _description = __doc__
    _name = 'calendar.todo.exrule'

TodoExRule()


class TodoAttendee(ModelSQL, ModelView):
    'Attendee'
    _description = __doc__
    _name = 'calendar.todo.attendee'
    _inherits = {'calendar.attendee': 'calendar_attendee'}

    calendar_attendee = fields.Many2One('calendar.attendee',
        'Calendar Attendee', required=True, ondelete='CASCADE', select=True)
    todo = fields.Many2One('calendar.todo', 'Todo', ondelete='CASCADE',
            required=True, select=True)

    def create(self, values):
        todo_obj = Pool().get('calendar.todo')

        if values.get('todo'):
            # Update write_date of todo
            todo_obj.write(values['todo'], {})
        res = super(TodoAttendee, self).create(values)
        attendee = self.browse(res)
        todo = attendee.todo
        if (todo.calendar.owner
                and (todo.organizer == todo.calendar.owner.email
                    or (todo.parent
                        and todo.parent.organizer == \
                            todo.parent.calendar.owner.email))):
            if todo.organizer == todo.calendar.owner.email:
                attendee_emails = [x.email for x in todo.attendees
                        if x.email != todo.organizer]
            else:
                attendee_emails = [x.email for x in todo.parent.attendees
                        if x.email != todo.parent.organizer]
            if attendee_emails:
                with Transaction().set_user(0):
                    todo_ids = todo_obj.search([
                        ('uuid', '=', todo.uuid),
                        ('calendar.owner.email', 'in', attendee_emails),
                        ('id', '!=', todo.id),
                        ('recurrence', '=', todo.recurrence),
                        ])
                    for todo_id in todo_ids:
                        self.copy(res, default={
                            'todo': todo_id,
                            })
        return res

    def write(self, ids, values):
        todo_obj = Pool().get('calendar.todo')

        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_ids = [x.todo.id for x in self.browse(ids)]
        if values.get('todo'):
            todo_ids.append(values['todo'])
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})

        if 'email' in values:
            values = values.copy()
            del values['email']

        res = super(TodoAttendee, self).write(ids, values)
        attendees = self.browse(ids)
        for attendee in attendees:
            todo = attendee.todo
            if todo.calendar.owner \
                    and (todo.organizer == todo.calendar.owner.email \
                    or (todo.parent \
                    and todo.parent.organizer == todo.calendar.owner.email)):
                if todo.organizer == todo.calendar.owner.email:
                    attendee_emails = [x.email for x in todo.attendees
                            if x.email != todo.organizer]
                else:
                    attendee_emails = [x.email for x in todo.parent.attendees
                            if x.email != todo.parent.organizer]
                if attendee_emails:
                    with Transaction().set_user(0):
                        attendee_ids = self.search([
                            ('todo.uuid', '=', todo.uuid),
                            ('todo.calendar.owner.email', 'in',
                                    attendee_emails),
                            ('id', '!=', attendee.id),
                            ('todo.recurrence', '=', todo.recurrence),
                            ('email', '=', attendee.email),
                            ])
                        self.write(attendee_ids, self._attendee2update(
                                attendee))
        return res

    def delete(self, ids):
        todo_obj = Pool().get('calendar.todo')
        attendee_obj = Pool().get('calendar.attendee')

        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_attendees = self.browse(ids)
        calendar_attendee_ids = [a.calendar_attendee.id \
                for a in todo_attendees]
        todo_ids = [x.todo.id for x in todo_attendees]
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})

        for attendee in self.browse(ids):
            todo = attendee.todo
            if todo.calendar.owner \
                    and (todo.organizer == todo.calendar.owner.email \
                    or (todo.parent \
                    and todo.parent.organizer == todo.calendar.owner.email)):
                if todo.organizer == todo.calendar.owner.email:
                    attendee_emails = [x.email for x in todo.attendees
                            if x.email != todo.organizer]
                else:
                    attendee_emails = [x.email for x in todo.attendees
                            if x.email != todo.parent.organizer]
                if attendee_emails:
                    with Transaction().set_user(0):
                        attendee_ids = self.search([
                            ('todo.uuid', '=', todo.uuid),
                            ('todo.calendar.owner.email', 'in',
                                attendee_emails),
                            ('id', '!=', attendee.id),
                            ('todo.recurrence', '=', todo.recurrence),
                            ('email', '=', attendee.email),
                            ])
                        self.delete(attendee_ids)
            elif todo.calendar.organizer \
                    and ((todo.organizer \
                    or (todo.parent and todo.parent.organizer)) \
                    and attendee.email == todo.calendar.owner.email):
                if todo.organizer:
                    organizer = todo.organizer
                else:
                    organizer = todo.parent.organizer
                with Transaction().set_user(0):
                    attendee_ids = self.search([
                        ('todo.uuid', '=', todo.uuid),
                        ('todo.calendar.owner.email', '=', organizer),
                        ('id', '!=', attendee.id),
                        ('todo.recurrence', '=', todo.recurrence),
                        ('email', '=', attendee.email),
                        ])
                    if attendee_ids:
                        self.write(attendee_ids, {
                            'status': 'declined',
                            })
        res = super(TodoAttendee, self).delete(ids)
        if calendar_attendee_ids:
            attendee_obj.delete(calendar_attendee_ids)
        return res

    def copy(self, ids, default=None):
        attendee_obj = Pool().get('calendar.attendee')

        int_id = False
        if isinstance(ids, (int, long)):
            int_id = True
            ids = [ids]
        if default is None:
            default = {}
        default = default.copy()
        new_ids = []
        for attendee in self.browse(ids):
            default['calendar_attendee'] = attendee_obj.copy(
                    attendee.calendar_attendee.id)
            new_id = super(TodoAttendee, self).copy(attendee.id,
                    default=default)
            new_ids.append(new_id)
        if int_id:
            return new_ids[0]
        return new_ids

    def _attendee2update(self, attendee):
        attendee_obj = Pool().get('calendar.attendee')
        return attendee_obj._attendee2update(attendee)

    def attendee2values(self, attendee):
        attendee_obj = Pool().get('calendar.attendee')
        return attendee_obj.attendee2values(attendee)

    def attendee2attendee(self, attendee):
        attendee_obj = Pool().get('calendar.attendee')
        return attendee_obj.attendee2attendee(attendee)

TodoAttendee()


class TodoAlarm(ModelSQL):
    'Alarm'
    _description = __doc__
    _name = 'calendar.todo.alarm'
    _inherits = {'calendar.alarm': 'calendar_alarm'}

    calendar_alarm = fields.Many2One('calendar.alarm', 'Calendar Alarm',
            required=True, ondelete='CASCADE', select=True)
    todo = fields.Many2One('calendar.todo', 'Todo', ondelete='CASCADE',
            required=True, select=True)

    def create(self, values):
        todo_obj = Pool().get('calendar.todo')
        if values.get('todo'):
            # Update write_date of todo
            todo_obj.write(values['todo'], {})
        return super(TodoAlarm, self).create(values)

    def write(self, ids, values):
        todo_obj = Pool().get('calendar.todo')
        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_ids = [x.todo.id for x in self.browse(ids)]
        if values.get('todo'):
            todo_ids.append(values['todo'])
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})
        return super(TodoAlarm, self).write(ids, values)

    def delete(self, ids):
        todo_obj = Pool().get('calendar.todo')
        alarm_obj = Pool().get('calendar.alarm')
        if isinstance(ids, (int, long)):
            ids = [ids]
        todo_alarms = self.browse(ids)
        alarm_ids = [a.calendar_alarm.id for a in todo_alarms]
        todo_ids = [x.todo.id for x in todo_alarms]
        if todo_ids:
            # Update write_date of todo
            todo_obj.write(todo_ids, {})
        res = super(TodoAlarm, self).delete(ids)
        if alarm_ids:
            alarm_obj.delete(alarm_ids)
        return res

    def valarm2values(self, alarm):
        alarm_obj = Pool().get('calendar.alarm')
        return alarm_obj.valarm2values(alarm)

    def alarm2valarm(self, alarm):
        alarm_obj = Pool().get('calendar.alarm')
        return alarm_obj.alarm2valarm(alarm)

TodoAlarm()
