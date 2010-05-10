# -*- coding: utf-8 -*-
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name' : 'Calendar Todo',
    'name_de_DE' : 'Kalender Aufgaben',
    'name_es_CO': 'Calendario de tareas',
    'name_es_ES': 'Calendario de tareas',
    'name_fr_FR' : 'Tâche Calendrier',
    'version' : '1.6.1',
    'author' : 'B2CK',
    'email': 'info@b2ck.com',
    'website': 'http://www.tryton.org/',
    'description': 'Add Todo support on CalDAV',
    'description_de_DE' : 'Fügt Unterstützung für Aufgaben in CalDAV hinzu',
    'description_es_CO': 'Añade soporte de tareas sobre CalDAV',
    'description_es_ES': 'Añade soporte de tareas sobre CalDAV',
    'description_fr_FR': 'Ajoute la gestion des tâches au CalDAV',
    'depends' : [
        'ir',
        'res',
        'webdav',
        'calendar',
    ],
    'xml' : [
        'todo.xml',
    ],
    'translation': [
        'de_DE.csv',
        'es_CO.csv',
        'es_ES.csv',
        'fr_FR.csv',
    ],
}
