{
    'name': 'Web Gantt',
    'category': 'Hidden',
    'description': """
OpenERP Web Gantt chart view.
=============================
The root element of gantt views is <gantt/>, it has no children but can take the
following attributes:

date_start (required)
    name of the field providing the start datetime of the event for each record.

date_stop
    name of the field providing the end duration of the event for each record.
    Can be replaced by date_delay. One (and only one) of date_stop and date_delay
    must be provided.
    If the field is False for a record, it’s assumed to be a “point event” and
    the end date will be set to the start date

date_delay
    name of the field providing the duration of the event

duration_unit
    one of minute, hour (default), day, week, month, year

progress
    name of a field providing the completion percentage for the record’s event,
    between 0 and 100

parent
    name of field providing who is the father of the event

links
    name of field providing dependency links to other events (one2many)

links_options
    dictionary with the following values

        * types: {
            "finish_to_start":"0",
            "start_to_start":"1",
            "finish_to_finish":"2",
            "start_to_finish":"3"
          }
        * type: name of field providing type value on relational model
        * source: (optional) name of the field that provides the origin event in
          the relational model, as default is the relation_field of the one2many
          field.
        * target: name of field providing dependent event on relational model
        * lag: (optional) name of the field that provides a positive or negative
          value that specifies the delay time between events involved in a link

options
    dictionary with the following values, these are use in 'gantt.config':

        * work_time: bool (default false)
        * correct_work_time: bool (default false)
        * skip_off_time: bool (default false)
        * server_utc: bool (default false)
        * open_tree_initially: bool (default false)
        * show_links: bool (default true if links defined, otherwise is false)
        * show_task_cells: bool (default true)
        * start_on_monday: bool (default true)
        * scale_offset_minimal: bool (default true)
        * min_duration: number of milliseconds (default 60 * 60 * 1000, 1 hour)
        * step: number (default 1)
        * duration_step: number (default 1)
        * time_step: number of minutes (default 60)
        * scale_unit: one of "minute", "hour", "day", "week", "quarter", "month",
          "year" (default "day")

        * date_scale: string with format date (default "%d %M")
        * date_grid: string with format date (default "%Y-%m-%d")
        * subscales: array of second time scales (default []).
          Each object in the array specifies a single scale. An object can take
          the following attributes:

            . format (string) the format of the scale's labels
            . step (string) the scale's step. By default, 1.
            . unit ("minute", "hour", "day", "week", "month", "year") the
              scale's unit. By default, "day"

""",
    'version': '2.0',
    'depends': ['web'],
    'data': [
        'views/web_gantt.xml',
    ],
    'qweb': [
        'static/src/xml/*.xml',
    ],
    'auto_install': False,
    'installable': True,
}
