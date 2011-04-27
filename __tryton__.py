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
    'version' : '2.0.1',
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
        'bg_BG.csv',
        'de_DE.csv',
        'es_CO.csv',
        'es_ES.csv',
        'fr_FR.csv',
        'ru_RU.csv',
    ],
}
