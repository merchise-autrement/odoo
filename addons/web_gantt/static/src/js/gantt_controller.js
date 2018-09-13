odoo.define('web_gantt.GanttController', function (require) {
"use strict";
/*---------------------------------------------------------
 * Odoo Gantt view
 *---------------------------------------------------------*/

var AbstractController = require('web.AbstractController');
var dialogs = require('web.view_dialogs');
var core = require('web.core');

var qweb = core.qweb;
var _t = core._t;

return AbstractController.extend({
    custom_events: _.extend({}, AbstractController.prototype.custom_events, {
        gantt_new_task:'_onGanttNewTask',
        gantt_open_task:'_onGanttOpenTask',
        gantt_delete_task:'_onGanttDeleteTask',
        gantt_update_task:'_onGanttUpdateTask',
        gantt_update_link:'_onGanttUpdateLink',
        gantt_open_link:'_onGanttOpenLink',
        gantt_new_link:'_onGanttNewLink',
        gantt_delete_link:'_onGanttDeleteLink',
        gantt_reload: '_onGanttReload'
    }),
    /**
     * @override
     * @param {Widget} parent
     */
    init: function () {
        this._super.apply(this, arguments);
    },

    /**
     * @override
     * Render gantt buttons
     */
    renderButtons: function ($node) {
        var self = this;
        this.$buttons = $(qweb.render("GanttView.buttons", {'widget': this}));

        this.$buttons.find('.o_gantt_button_scale').bind('click', function (event) {
            return self._onClickScaleButton(event);
        });
        if ($node) {
            this.$buttons.appendTo($node);
        }
    },

    /**
     * @event
     *
     * Reload all Gantt.
     */
    _onGanttReload: function(event){
        this.reload();
    },

    /**
     * @event
     *
     * Create new task.
     */
    _onGanttNewTask: function(event){
        event.stopPropagation();
        this.trigger_up('switch_view', {view_type: 'form', res_id: undefined});
    },

    /**
     * @event
     *
     * Open task.
     */
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

    /**
     * @event
     *
     * Update task.
     */
    _onGanttUpdateTask: function(event){
        this.model.saveTask(event.data.task);
    },

    /**
     * @event
     *
     * Open link.
     */
    _onGanttOpenLink: function(event){
        event.stopPropagation();
        var self = this;
        var dialog = new dialogs.FormViewDialog(this, {
            shouldSaveLocally: true, // update links on chart gantt will write on model
            res_model: this.model.linkModel,
            mode: event.data.mode,
            res_id: parseInt(event.data.id),
            title: _t("Edit link"),
            on_saved: function(record){
                this.close();
                self.trigger_up('gantt_reload');
            }
        });
        dialog.buttons.push({
            text: _t("Delete"),
            classes: "btn-warning pull-right",
            close: true,
            click: function(){
                self.deleteGanttLink(event.data.id);
            },
        });
        dialog.open();
    },

    /**
     * @event
     *
     * Update link.
     */
    _onGanttUpdateLink: function(event){
        this.model.saveLink(event.data.link);
    },

    /**
     * @event
     *
     * Create new link.
     */
    _onGanttNewLink: function(event){
        var self = this;
        this.model.saveLink(event.data.link).then(function(new_id){
            if (typeof new_id === 'number'){
                self.renderer.executeGanttFunction('changeLinkId', event.data.link.id,new_id);
            }
        });
    },

    /**
     * @event
     *
     * Delete link.
     */
    _onGanttDeleteLink: function(event){
        this.model.deleteLink(event.data.link);
    },

    /**
     * @event
     *
     * Set gantt scale.
     */
    _onClickScaleButton: function (e) {
        var scale = e.target.value;
        this.renderer.setScale(scale);
    },

    deleteGanttLink:function(linkId){
        this.renderer.executeGanttFunction('deleteLink', linkId);
    },

});

});