#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
import vobject
import urllib
from pywebdav.lib.errors import DAV_NotFound, DAV_Forbidden
from trytond.model import ModelView, ModelSQL
from trytond.tools import reduce_ids
from trytond.transaction import Transaction
from trytond.cache import Cache
from trytond.pool import Pool


class Collection(ModelSQL, ModelView):

    _name = "webdav.collection"

    @Cache('webdav_collection.todo')
    def todo(self, uri, calendar_id=False):
        '''
        Return the todo id in the uri

        :param uri: the uri
        :param calendar_id: the calendar id
        :return: todo id
            or None if there is no todo
        '''
        todo_obj = Pool().get('calendar.todo')

        if uri and uri.startswith('Calendars/'):
            calendar, todo_uri = (uri[10:].split('/', 1) + [None])[0:2]
            if not calendar_id:
                calendar_id = self.calendar(uri)
                if not calendar_id:
                    return None
            todo_ids = todo_obj.search([
                ('calendar', '=', calendar_id),
                ('uuid', '=', todo_uri[:-4]),
                ('parent', '=', None),
                ], limit=1)
            if todo_ids:
                return todo_ids[0]

    def _caldav_filter_domain_todo(self, filter):
        '''
        Return a domain for caldav filter on todo

        :param filter: the DOM Element of filter
        :return: a list for domain
        '''
        res = []
        if not filter:
            return []
        if filter.localName == 'principal-property-search':
            return [('id', '=', 0)]
        elif filter.localName == 'calendar-query':
            calendar_filter = None
            for e in filter.childNodes:
                if e.nodeType == e.TEXT_NODE:
                    continue
                if e.localName == 'filter':
                    calendar_filter = e
                    break
            if calendar_filter is None:
                return []
            for vcalendar_filter in calendar_filter.childNodes:
                if vcalendar_filter.nodeType == vcalendar_filter.TEXT_NODE:
                    continue
                if vcalendar_filter.getAttribute('name') != 'VCALENDAR':
                    return [('id', '=', 0)]
                vtodo_filter = None
                for vtodo_filter in vcalendar_filter.childNodes:
                    if vtodo_filter.nodeType == vtodo_filter.TEXT_NODE:
                        vtodo_filter = None
                        continue
                    if vtodo_filter.localName == 'comp-filter':
                        if vtodo_filter.getAttribute('name') != 'VTODO':
                            vtodo_filter = None
                            continue
                        break
                if vtodo_filter is None:
                    return [('id', '=', 0)]
                break
            return []
        elif filter.localName == 'calendar-multiget':
            ids = []
            for e in filter.childNodes:
                if e.nodeType == e.TEXT_NODE:
                    continue
                if e.localName == 'href':
                    if not e.firstChild:
                        continue
                    uri = e.firstChild.data
                    dbname, uri = (uri.lstrip('/').split('/', 1) + [None])[0:2]
                    if not dbname:
                        continue
                    dbname == urllib.unquote_plus(dbname)
                    if dbname != Transaction().cursor.database_name:
                        continue
                    if uri:
                        uri = urllib.unquote_plus(uri)
                    todo_id = self.todo(uri)
                    if todo_id:
                        ids.append(todo_id)
            return [('id', 'in', ids)]
        return res

    def get_childs(self, uri, filter=None, cache=None):
        todo_obj = Pool().get('calendar.todo')

        res = super(Collection, self).get_childs(uri, filter=filter,
                cache=cache)

        if uri and (uri not in ('Calendars', 'Calendars/')) and \
                uri.startswith('Calendars/'):
            calendar_id = self.calendar(uri)
            if  calendar_id and not (uri[10:].split('/', 1) + [None])[1]:
                domain = self._caldav_filter_domain_todo(filter)
                todo_ids = todo_obj.search([
                    ('calendar', '=', calendar_id),
                    domain,
                    ])
                todos = todo_obj.browse(todo_ids)
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(todo_obj._name, {})
                    for todo_id in todo_ids:
                        cache['_calendar'][todo_obj._name][todo_id] = {}
                return res + [x.uuid + '.ics' for x in todos]

        return res

    def get_resourcetype(self, uri, cache=None):
        from DAV.constants import COLLECTION, OBJECT
        if uri in ('Calendars', 'Calendars/'):
            return COLLECTION
        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return COLLECTION
            if self.todo(uri, calendar_id=calendar_id):
                return OBJECT
        elif self.calendar(uri, ics=True):
            return OBJECT
        return super(Collection, self).get_resourcetype(uri, cache=cache)

    def get_contenttype(self, uri, cache=None):
        if self.todo(uri) \
                or self.calendar(uri, ics=True):
            return 'text/calendar'
        return super(Collection, self).get_contenttype(uri, cache=cache)

    def get_creationdate(self, uri, cache=None):
        todo_obj = Pool().get('calendar.todo')

        cursor = Transaction().cursor

        calendar_id = self.calendar(uri)
        if not calendar_id:
            calendar_id = self.calendar(uri, ics=True)
        if calendar_id and (uri[10:].split('/', 1) + [None])[1]:

            todo_id = self.todo(uri, calendar_id=calendar_id)
            if todo_id:
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(todo_obj._name, {})
                    ids = cache['_calendar'][todo_obj._name].keys()
                    if todo_id not in ids:
                        ids.append(todo_id)
                    elif 'creationdate' in cache['_calendar'][
                            todo_obj._name][todo_id]:
                        return cache['_calendar'][todo_obj._name][
                            todo_id]['creationdate']
                else:
                    ids = [todo_id]
                res = None
                for i in range(0, len(ids), cursor.IN_MAX):
                    sub_ids = ids[i:i + cursor.IN_MAX]
                    red_sql, red_ids = reduce_ids('id', sub_ids)
                    cursor.execute('SELECT id, ' \
                            'EXTRACT(epoch FROM create_date) ' \
                        'FROM "' + todo_obj._table + '" ' \
                        'WHERE ' + red_sql, red_ids)
                    for todo_id2, date in cursor.fetchall():
                        if todo_id2 == todo_id:
                            res = date
                        if cache is not None:
                            cache['_calendar'][todo_obj._name]\
                                    .setdefault(todo_id2, {})
                            cache['_calendar'][todo_obj._name][
                                todo_id2]['creationdate'] = date
                if res is not None:
                    return res

        return super(Collection, self).get_creationdate(uri, cache=cache)

    def get_lastmodified(self, uri, cache=None):
        todo_obj = Pool().get('calendar.todo')

        cursor = Transaction().cursor

        calendar_id = self.calendar(uri)
        if calendar_id and (uri[10:].split('/', 1) + [None])[1]:
            todo_id = self.todo(uri, calendar_id=calendar_id)
            if todo_id:
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(todo_obj._name, {})
                    ids = cache['_calendar'][todo_obj._name].keys()
                    if todo_id not in ids:
                        ids.append(todo_id)
                    elif 'lastmodified' in cache['_calendar'][
                            todo_obj._name][todo_id]:
                        return cache['_calendar'][todo_obj._name][
                            todo_id]['lastmodified']
                else:
                    ids = [todo_id]
                res = None
                for i in range(0, len(ids), cursor.IN_MAX / 2):
                    sub_ids = ids[i:i + cursor.IN_MAX / 2]
                    red_id_sql, red_id_ids = reduce_ids('id', sub_ids)
                    red_parent_sql, red_parent_ids = reduce_ids('parent',
                            sub_ids)
                    cursor.execute('SELECT COALESCE(parent, id), ' \
                                'MAX(EXTRACT(epoch FROM ' \
                                'COALESCE(write_date, create_date))) ' \
                            'FROM "' + todo_obj._table + '" ' \
                            'WHERE ' + red_id_sql + ' ' \
                                'OR ' + red_parent_sql + ' ' \
                            'GROUP BY parent, id', red_id_ids + red_parent_ids)
                    for todo_id2, date in cursor.fetchall():
                        if todo_id2 == todo_id:
                            res = date
                        if cache is not None:
                            cache['_calendar'][todo_obj._name]\
                                    .setdefault(todo_id2, {})
                            cache['_calendar'][todo_obj._name][
                                todo_id2]['lastmodified'] = date
                if res is not None:
                    return res

        return super(Collection, self).get_lastmodified(uri, cache=cache)

    def get_data(self, uri, cache=None):
        todo_obj = Pool().get('calendar.todo')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_NotFound
            todo_id = self.todo(uri, calendar_id=calendar_id)
            if not todo_id:
                return super(Collection, self).get_data(uri, cache=cache)
            ical = todo_obj.todo2ical(todo_id)
            return ical.serialize()

        return super(Collection, self).get_data(uri, cache=cache)

    def put(self, uri, data, content_type, cache=None):
        todo_obj = Pool().get('calendar.todo')
        calendar_obj = Pool().get('calendar.calendar')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_Forbidden
            todo_id = self.todo(uri, calendar_id=calendar_id)
            ical = vobject.readOne(data)
            if not hasattr(ical, 'vtodo'):
                return super(Collection, self).put(uri, data, content_type)

            if not todo_id:

                values = todo_obj.ical2values(None, ical, calendar_id)
                todo_id = todo_obj.create(values)
                todo = todo_obj.browse(todo_id)
                calendar = calendar_obj.browse(calendar_id)
                return Transaction().cursor.database_name + '/Calendars/' + \
                        calendar.name + '/' + todo.uuid + '.ics'
            else:
                values = todo_obj.ical2values(todo_id, ical, calendar_id)
                todo_obj.write(todo_id, values)
                return

        return super(Collection, self).put(uri, data, content_type)

    def rm(self, uri, cache=None):
        todo_obj = Pool().get('calendar.todo')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_Forbidden
            todo_id = self.todo(uri, calendar_id=calendar_id)
            if todo_id:
                try:
                    todo_obj.delete(todo_id)
                except Exception:
                    raise DAV_Forbidden
                return 200
        return super(Collection, self).rm(uri, cache=cache)

    def exists(self, uri, cache=None):
        if uri in ('Calendars', 'Calendars/'):
            return 1
        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return 1
            if self.todo(uri, calendar_id=calendar_id):
                return 1
        return super(Collection, self).exists(uri, cache=cache)

Collection()
