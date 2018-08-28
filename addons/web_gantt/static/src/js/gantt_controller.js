odoo.define('web_gantt.GanttController', function (require) {
"use strict";
/*---------------------------------------------------------
 * Odoo Gantt view
 *---------------------------------------------------------*/

var AbstractController = require('web.AbstractController');
var core = require('web.core');

var qweb = core.qweb;

return AbstractController.extend({
    className: 'oe_gantt',
    custom_events: _.extend({}, AbstractController.prototype.custom_events, {
        gantt_new_task:'_onGanttNewTask',
        gantt_open_task:'_onGanttOpenTask',
        gantt_delete_task:'_onGanttDeleteTask',
        gantt_update_task:'_onGanttUpdateTask',
        gantt_update_link:'_onGanttUpdateLink',
        gantt_new_link:'_onGanttNewLink',
        gantt_delete_link:'_onGanttDeleteLink',
    }),
    /**
     * @override
     * @param {Widget} parent
     */
    init: function () {
        this._super.apply(this, arguments);
    },

    _onGanttNewTask: function(event){
        event.stopPropagation();
        this.trigger_up('switch_view', {view_type: 'form', res_id: undefined});
    },

    _onGanttOpenTask: function(event){
        event.stopPropagation();
        var record = this.model.get(event.data.id, {raw: true});
        this.trigger_up('switch_view', {
            view_type: 'form',
            res_id: record.res_id,
            mode: event.data.mode || 'readonly',
            model: this.modelName,
        });
    },

    _onGanttUpdateTask: function(event){
        this.model.saveTask(event.data.task);
    },

    _onGanttUpdateLink: function(event){
        this.model.saveLink(event.data.link);
    },

    _onGanttNewLink: function(event){
        this.model.saveLink(event.data.link);
    },

    _onGanttDeleteLink: function(event){
        this.model.deleteLink(event.data.link);
    }

});

});