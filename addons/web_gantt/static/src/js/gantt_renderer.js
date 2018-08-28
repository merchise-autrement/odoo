odoo.define('web_gantt.GanttRenderer', function (require) {
"use strict";

var AbstractRenderer = require('web.AbstractRenderer');
var config = require('web.config');
var core = require('web.core');
var field_utils = require('web.field_utils');

var _t = core._t;
var qweb = core.qweb;

return AbstractRenderer.extend({
    className: 'o_gantt_container',
    /**
     * @override
     * @param {Widget} parent
     */
    init: function (parent, state, params) {
        this._super.apply(this, arguments);
        this.gantt_id = _.uniqueId();
        this.ganttConfig = params.config;
    },

    _render: function () {
        this._renderGantt();
        return this._super.apply(this, arguments);
    },

    _renderGantt: function(){
        this.$el.empty();
        var self = this;
        this.$div_with_id = $('<div>').attr('id', this.gantt_id).attr('style',"width:100%; height:100%;");
        this.$el.append(this.$div_with_id)
        this.configGantt();
        gantt.init(this.$div_with_id[0]);
        setTimeout(function(){
            gantt.clearAll();
            gantt.parse(self.state.gantt.data);
        },100);
    },

    configGantt: function(){
        this._configGantt();
        gantt.showLightbox = function(id){
            var task = gantt.getTask(id);
            if (task.$new){
                self.newTask(task);
            }
            else self.openTask(task);
            return false;
        }
        this._configEvents();
    },

    _configGantt: function(){
        var self = this;
        _.each(this.ganttConfig, function(value, key){
            gantt.config[key] = value;
        });
    },

    _configEvents: function(){
        var self = this;
        var events = {
            onTaskCreated: function(task){
                self.newTask(task);
            },
            onAfterTaskUpdate: function(id, task){
                self.updateTask(task);
            },
            onAfterTaskDelete: function(id, task){
                self.deleteTask(task);
            },
            onAfterLinkAdd: function(id, link){
                self.newLink(link);
            },
            onAfterLinkUpdate: function(id, link){
                self.updateLink(link);
            },
            onAfterLinkDelete: function(id, link){
                self.deleteLink(link);
            },
            onBeforeLinkAdd: function(id, link){
                link.$new = true;
                return true;
            },
        };

        // attach all events
        _.each(events, function(fn,e){
            gantt.attachEvent(e,fn);
        })

    },

    openTask: function (task) {
        this.trigger_up('gantt_open_task', {
            id: task.id,
            mode: 'edit',
        });
    },

    newTask: function(task){
        this.trigger_up('gantt_new_task', {});
    },

    updateTask: function(task){
        this.trigger_up('gantt_update_task', {task: task});
    },

    deleteTask: function(task){
        this.trigger_up('gantt_delete_task', {task: task});
    },

    newLink: function(link){
        this.trigger_up('gantt_new_link', {link:link});
    },

    updateLink: function(link){
        this.trigger_up('gantt_update_link', {link: link});
    },

    deleteLink: function(link){
        this.trigger_up('gantt_delete_link', {link: link});
    },
});

});