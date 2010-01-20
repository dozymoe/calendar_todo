#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelView, ModelSQL
from trytond.tools import Cache, reduce_ids
from DAV.errors import DAV_NotFound, DAV_Forbidden
import vobject
import urllib


class Collection(ModelSQL, ModelView):

    _name = "webdav.collection"

    @Cache('webdav_collection.todo')
    def todo(self, cursor, user, uri, calendar_id=False, context=None):
        '''
        Return the todo id in the uri or False

        :param cursor: the database cursor
        :param user: the user id
        :param uri: the uri
        :param calendar_id: the calendar id
        :param context: the context
        :return: todo id
            or False if there is no todo
        '''
        todo_obj = self.pool.get('calendar.todo')

        if uri and uri.startswith('Calendars/'):
            calendar, todo_uri = (uri[10:].split('/', 1) + [None])[0:2]
            if not calendar_id:
                calendar_id = self.calendar(cursor, user, uri, context=context)
                if not calendar_id:
                    return False
            todo_ids = todo_obj.search(cursor, user, [
                ('calendar', '=', calendar_id),
                ('uuid', '=', todo_uri[:-4]),
                ('parent', '=', False),
                ], limit=1, context=context)
            if todo_ids:
                return todo_ids[0]
        return False

    def _caldav_filter_domain_todo(self, cursor, user, filter, context=None):
        '''
        Return a domain for caldav filter on todo

        :param cursor: the database cursor
        :param user: the user id
        :param filter: the DOM Element of filter
        :param context: the context
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
                    if dbname != cursor.database_name:
                        continue
                    if uri:
                        uri = urllib.unquote_plus(uri)
                    todo_id = self.todo(cursor, user, uri, context=context)
                    if todo_id:
                        ids.append(todo_id)
            return [('id', 'in', ids)]
        return res

    def get_childs(self, cursor, user, uri, filter=None, context=None,
            cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        todo_obj = self.pool.get('calendar.todo')

        res = super(Collection, self).get_childs(cursor, user, uri,
                filter=filter, context=context, cache=cache)

        if uri and (uri not in ('Calendars', 'Calendars/')) and \
                uri.startswith('Calendars/'):
            calendar_id = self.calendar(cursor, user, uri, context=context)
            if  calendar_id and not (uri[10:].split('/', 1) + [None])[1]:
                domain = self._caldav_filter_domain_todo(cursor, user, filter,
                        context=context)
                todo_ids = todo_obj.search(cursor, user, [
                    ('calendar', '=', calendar_id),
                    domain,
                    ], context=context)
                todos = todo_obj.browse(cursor, user, todo_ids,
                        context=context)
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(todo_obj._name, {})
                    for todo_id in todo_ids:
                        cache['_calendar'][todo_obj._name][todo_id] = {}
                return res + [x.uuid + '.ics' for x in todos]

        return res

    def get_resourcetype(self, cursor, user, uri, context=None, cache=None):
        from DAV.constants import COLLECTION, OBJECT
        if uri in ('Calendars', 'Calendars/'):
            return COLLECTION
        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return COLLECTION
            if self.todo(cursor, user, uri, calendar_id=calendar_id,
                    context=context):
                return OBJECT
        elif self.calendar(cursor, user, uri, ics=True, context=context):
            return OBJECT
        return super(Collection, self).get_resourcetype(cursor, user, uri,
                context=context, cache=cache)

    def get_contenttype(self, cursor, user, uri, context=None, cache=None):
        if self.todo(cursor, user, uri, context=context) \
                or self.calendar(cursor, user, uri, ics=True, context=context):
            return 'text/calendar'
        return super(Collection, self).get_contenttype(cursor, user, uri,
                context=context, cache=cache)

    def get_creationdate(self, cursor, user, uri, context=None, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        todo_obj = self.pool.get('calendar.todo')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if not calendar_id:
            calendar_id = self.calendar(cursor, user, uri, ics=True,
                    context=context)
        if calendar_id and (uri[10:].split('/', 1) + [None])[1]:

            todo_id = self.todo(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if todo_id:
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(todo_obj._name, {})
                    ids = cache['_calendar'][todo_obj._name].keys()
                    if todo_id not in ids:
                        ids.append(todo_id)
                    elif 'creationdate' in cache['_calendar']\
                            [todo_obj._name][todo_id]:
                        return cache['_calendar'][todo_obj._name]\
                                [todo_id]['creationdate']
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
                            cache['_calendar'][todo_obj._name]\
                                    [todo_id2]['creationdate'] = date
                if res is not None:
                    return res

        return super(Collection, self).get_creationdate(cursor, user, uri,
                context=context, cache=cache)

    def get_lastmodified(self, cursor, user, uri, context=None, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        todo_obj = self.pool.get('calendar.todo')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id and (uri[10:].split('/', 1) + [None])[1]:
            todo_id = self.todo(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if todo_id:
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(todo_obj._name, {})
                    ids = cache['_calendar'][todo_obj._name].keys()
                    if todo_id not in ids:
                        ids.append(todo_id)
                    elif 'lastmodified' in cache['_calendar']\
                            [todo_obj._name][todo_id]:
                        return cache['_calendar'][todo_obj._name]\
                                [todo_id]['lastmodified']
                else:
                    ids = [todo_id]
                res = None
                for i in range(0, len(ids), cursor.IN_MAX/2):
                    sub_ids = ids[i:i + cursor.IN_MAX/2]
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
                            cache['_calendar'][todo_obj._name]\
                                    [todo_id2]['lastmodified'] = date
                if res is not None:
                    return res

        return super(Collection, self).get_lastmodified(cursor, user, uri,
                context=context, cache=cache)

    def get_data(self, cursor, user, uri, context=None, cache=None):
        todo_obj = self.pool.get('calendar.todo')
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_NotFound
            todo_id = self.todo(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if not todo_id:
                return super(Collection, self).get_data(cursor, user, uri,
                        context=context, cache=cache)
            ical = todo_obj.todo2ical(cursor, user, todo_id, context=context)
            return ical.serialize()

        return super(Collection, self).get_data(cursor, user, uri,
                context=context, cache=cache)

    def put(self, cursor, user, uri, data, content_type, context=None,
            cache=None):
        todo_obj = self.pool.get('calendar.todo')
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_Forbidden
            todo_id = self.todo(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            ical = vobject.readOne(data)
            if not hasattr(ical, 'vtodo'):
                return super(Collection, self).put(cursor, user, uri, data,
                        content_type, context=context)

            if not todo_id:

                values = todo_obj.ical2values(cursor, user, None, ical,
                        calendar_id, context=context)
                todo_id = todo_obj.create(cursor, user, values,
                        context=context)
                todo = todo_obj.browse(cursor, user, todo_id,
                        context=context)
                calendar = calendar_obj.browse(cursor, user, calendar_id,
                        context=context)
                return cursor.database_name + '/Calendars/' + calendar.name + \
                        '/' + todo.uuid + '.ics'
            else:
                values = todo_obj.ical2values(cursor, user, todo_id, ical,
                        calendar_id, context=context)
                todo_obj.write(cursor, user, todo_id, values,
                        context=context)
                return

        return super(Collection, self).put(cursor, user, uri, data,
                content_type, context=context)

    def rm(self, cursor, user, uri, context=None, cache=None):
        todo_obj = self.pool.get('calendar.todo')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_Forbidden
            todo_id = self.todo(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if todo_id:
                try:
                    todo_obj.delete(cursor, user, todo_id, context=context)
                except:
                    raise DAV_Forbidden
                return 200
        return super(Collection, self).rm(cursor, user, uri, context=context,
                cache=cache)

    def exists(self, cursor, user, uri, context=None, cache=None):
        if uri in ('Calendars', 'Calendars/'):
            return 1
        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return 1
            if self.todo(cursor, user, uri, calendar_id=calendar_id,
                    context=context):
                return 1
        return super(Collection, self).exists(cursor, user, uri, context=context,
                cache=cache)

Collection()
