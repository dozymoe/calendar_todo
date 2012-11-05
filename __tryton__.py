# -*- coding: utf-8 -*-
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name' : 'Calendar Todo',
    'name_bg_BG' : 'Задачи за календар',
    'name_de_DE' : 'Kalender Aufgaben',
    'name_es_CO': 'Calendario de tareas',
    'name_es_ES': 'Calendario de tareas',
    'name_fr_FR' : 'Tâche Calendrier',
    'name_ru_RU' : 'Задачи для календаря',
    'version': '2.2.3',
    'author' : 'B2CK',
    'email': 'info@b2ck.com',
    'website': 'http://www.tryton.org/',
    'description': 'Add Todo support on CalDAV',
    'description_bg_BG' : 'Добавя поддръжка на задачи в CalDAV',
    'description_de_DE' : 'Fügt Unterstützung für Aufgaben in CalDAV hinzu',
    'description_es_CO': 'Añade soporte de tareas sobre CalDAV',
    'description_es_ES': 'Añade soporte de tareas sobre CalDAV',
    'description_fr_FR': 'Ajoute la gestion des tâches au CalDAV',
    'description_ru_RU' : 'Добавление поддержки задач для CalDAV',
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
        'locale/bg_BG.po',
        'locale/cs_CZ.po',
        'locale/de_DE.po',
        'locale/es_CO.po',
        'locale/es_ES.po',
        'locale/fr_FR.po',
        'locale/nl_NL.po',
        'locale/ru_RU.po',
    ],
}
