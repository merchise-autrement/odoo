odoo.define('web_gantt.GanttView', function (require) {
"use strict";

var view_registry = require('web.view_registry');

var AbstractView = require('web.AbstractView');
var core = require('web.core');
var GanttModel = require('web_gantt.GanttModel');
var GanttController = require('web_gantt.GanttController');
var GanttRenderer = require('web_gantt.GanttRenderer');


var _t = core._t;
var _lt = core._lt;

// gather the fields to get
var fieldsToGather = {
    "date_start": "start_date",
    "date_delay": "duration",
    "date_stop": "end_date",
    "parent": "parent"
}

var fieldsDefaults = {
    "parent": "parent_id",
    "date_stop": "end_date",
    "date_delay": "duration",
}

var link_types = {
    "finish_to_start":"0",
    "start_to_start":"1",
    "finish_to_finish":"2",
    "start_to_finish":"3"
};

var links_properties = {
    "source": "source",
    "target": "target",
    "type": "type",
}

var configsOdoo = {
    duration_unit: "hour",
    server_utc: true,
    xml_date: "%Y-%m-%d %H:%i:%s",
    show_links:false,
}

var GraphView = AbstractView.extend({
    display_name: _lt('Gantt'),
    icon: 'fa-tasks',
    template: 'GanttView',
    cssLibs: [
        '/web_gantt/static/lib/dhtmlxGantt/codebase/dhtmlxgantt.css'
    ],
    jsLibs: [
        '/web_gantt/static/lib/dhtmlxGantt/codebase/dhtmlxgantt.js',
    ],
    config: {
        Model: GanttModel,
        Controller: GanttController,
        Renderer: GanttRenderer,
    },
    init: function(viewInfo, params) {
        this._super.apply(this, arguments);
        var arch = viewInfo.arch;
        var fields = viewInfo.fields;
        var attrs = arch.attrs;
        // Warning: quotes and double quotes problem due to json and xml clash
        var options = JSON.parse(attrs.options ? attrs.options.replace(/'/g, '"') : '{}');
        if (!attrs.date_start) {
            throw new Error(_lt("Gantt view has not defined 'date_start' attribute."));
        }

        var mapping = {};
        var fieldNames = fields.display_name ? ['display_name'] : [];
        mapping['text'] = 'display_name';
        mapping['id'] = 'id';

        if(attrs.links){
            fieldNames.push(attrs.links);
            configsOdoo.show_links = true;
        }

        var groupBy = arch.attrs.default_group_by ? [arch.attrs.default_group_by] : (params.groupBy || [])
        fieldNames.concat(groupBy);
        _.each(fieldsToGather, function (gantt_field, field) {
            if (arch.attrs[field]) {
                var fieldName = attrs[field];
            }
            else{
                var fieldName = fieldsDefaults[field];
            }
            fieldNames.push(fieldName);
            mapping[gantt_field] = fieldName;
        });

        this.rendererParams.config = _.extend(configsOdoo, options);
        this.rendererParams.model = viewInfo.model;

        this.controllerParams.mapping = mapping;
        this.controllerParams.context = params.context || {};
        this.controllerParams.displayName = params.action && params.action.name;

        this.loadParams.fieldNames = _.uniq(fieldNames);
        this.loadParams.fields = fields;
        this.loadParams.mapping = mapping;
        this.loadParams.fieldsInfo = viewInfo.fieldsInfo;
        this.loadParams.initialDate = moment(params.initialDate || new Date());
        this.loadParams.groupBy = groupBy;
        this.loadParams.links = attrs.links;
        if (attrs.links){
            var links_options = JSON.parse(attrs.links_options ? attrs.links_options.replace(/'/g, '"') : '{}');
            if (links_options.types){
                this.rendererParams.config.links = links_options.types;
            }
            this.loadParams.links_options = _.extend(links_properties, links_options);
        }
    },

    // TODO: make sure fields name are in respectively models.
});

view_registry.add('gantt', GraphView);

return GraphView;

})
