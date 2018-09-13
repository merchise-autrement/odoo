odoo.define('web_gantt.GanttRenderer', function (require) {
"use strict";

var AbstractRenderer = require('web.AbstractRenderer');
var config = require('web.config');
var core = require('web.core');
var field_utils = require('web.field_utils');
var ajax = require('web.ajax');
var session = require('web.session');
var _t = core._t;
var qweb = core.qweb;

return AbstractRenderer.extend({
    className: 'o_gantt_container',

    /**
     * @override
     * @constructor
     * @param {Widget} parent
     * @param {Object} state
     * @param {Object} params
     */
    init: function (parent, state, params) {
        this._super.apply(this, arguments);
        this.gantt_id = _.uniqueId();
        this.ganttConfig = params.config;
        this.$div_with_id = $('<div>').attr('id', this.gantt_id).attr('style',"width:100%; height:100%;");
        if (this.arch.attrs.x2manyField)
            this.$div_with_id.height(500);
    },

    /**
     * @override
     */
    _render: function () {
        this._renderGantt();
        return this._super.apply(this, arguments);
    },

    /**
     * @private
     *
     * Initialize the gantt
     */
    _renderGantt: function(){
        this.$el.empty();
        var self = this;
        this.$el.append(this.$div_with_id)
        this.configGantt();
        gantt.init(this.$div_with_id[0]);
        setTimeout(function(){
            gantt.clearAll();
            gantt.parse(self.state.gantt.data);
        },100);
    },

    /**
     * @public
     *
     * Set configurations and events to gantt chart.
     */
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

    /**
     * @private
     *
     * Set configurations to gantt chart.
     */
    _configGantt: function(){
        var self = this;
        _.each(this.ganttConfig, function(value, key){
            gantt.config[key] = value;
        });
        gantt.templates.tooltip_text = this.tooltipTask;
    },

    /**
     * @private
     *
     * Set events to gantt chart.
     */
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
            onLinkDblClick: function(id, e){
                self.openLink(id);
                return false;
            },
        };

        // attach all events
        _.each(events, function(fn,e){
            gantt.attachEvent(e,fn);
        })

    },

    /**
     * Open selected task in a form view.
     */
    openTask: function (task) {
        this.trigger_up('gantt_open_task', {
            id: task.id,
            mode: 'edit',
        });
    },

    /**
     * Open a form view to create new task.
     */
    newTask: function(task){
        this.trigger_up('gantt_new_task', {});
    },

    /**
     * Update task values.
     */
    updateTask: function(task){
        this.trigger_up('gantt_update_task', {task: task});
    },

    /**
     * Unlink task.
     */
    deleteTask: function(task){
        this.trigger_up('gantt_delete_task', {task: task});
    },

    /**
     * Open selected link in a form view.
     */
    openLink: function(link_id){
        this.trigger_up('gantt_open_link', {
            mode: 'edit',
            id:link_id,
        });
    },

    /**
     * Create new link.
     */
    newLink: function(link){
        this.trigger_up('gantt_new_link', {link:link});
    },

    /**
     * Update link values.
     */
    updateLink: function(link){
        this.trigger_up('gantt_update_link', {link: link});
    },

    /**
     * Unlink link.
     */
    deleteLink: function(link){
        this.trigger_up('gantt_delete_link', {link: link});
    },

    /**
     * This method render gantt with select scale.
     */
    setScale: function(scale){
        switch (scale) {
            case "hour":
                gantt.config.scale_unit = "hour";
                gantt.config.step = 1;
                gantt.config.date_scale = '%H:%i';
                gantt.config.subscales = [
                    {unit:"day", step:1, date:"%d %M"}
                ];
                break;
            case "day":
                gantt.config.scale_unit = "day";
                gantt.config.step = 1;
                gantt.config.date_scale = "%d %M";
                gantt.config.subscales = [];
                break;
            case "month":
                gantt.config.scale_unit = "month";
                gantt.config.date_scale = "%F, %Y";
                gantt.config.subscales = [
                    {unit: "day", step: 1, date: "%j, %D"}
                ];
                break;
            case "year":
                gantt.config.scale_unit = "year";
                gantt.config.step = 1;
                gantt.config.date_scale = "%Y";
                gantt.config.subscales = [
                    {unit: "month", step: 1, date: "%M"}
                ];
                break;
        }
        gantt.render();
    },

    /**
     * @override
     * Set locale and then call super.
     */
    willStart: function () {
        var self = this;
        var defs = [];
        defs.push(this._super());
        defs.push(this.setLocale());
        return $.when.apply($, defs);
    },

    /**
     * Load the correct locale
     */
    setLocale: function(){
        var gantt_path = '/web_gantt/static/lib/dhtmlxGantt';
        var locales_mapping = {
            'ar_SY': 'ar', 'ca_ES': 'ca', 'zh_CN': 'cn', 'cs_CZ': 'cs', 'da_DK': 'da',
            'de_DE': 'de', 'el_GR': 'el', 'es_ES': 'es', 'fi_FI': 'fi', 'fr_FR': 'fr',
            'he_IL': 'he', 'hu_HU': 'hu', 'id_ID': 'id', 'it_IT': 'it', 'ja_JP': 'jp',
            'ko_KR': 'kr', 'nl_NL': 'nl', 'nb_NO': 'no', 'pl_PL': 'pl', 'pt_PT': 'pt',
            'ro_RO': 'ro', 'ru_RU': 'ru', 'sl_SI': 'si', 'sk_SK': 'sk', 'sv_SE': 'sv',
            'tr_TR': 'tr', 'uk_UA': 'ua',
            'ar': 'ar', 'ca': 'ca', 'zh': 'cn', 'cs': 'cs', 'da': 'da', 'de': 'de',
            'el': 'el', 'es': 'es', 'fi': 'fi', 'fr': 'fr', 'he': 'he', 'hu': 'hu',
            'id': 'id', 'it': 'it', 'ja': 'jp', 'ko': 'kr', 'nl': 'nl', 'nb': 'no',
            'pl': 'pl', 'pt': 'pt', 'ro': 'ro', 'ru': 'ru', 'sl': 'si', 'sk': 'sk',
            'sv': 'sv', 'tr': 'tr', 'uk': 'ua',
        };

        var current_locale = session.user_context.lang;
        var current_short_locale = current_locale.split('_')[0];
        var locale_code = locales_mapping[current_locale] || locales_mapping[current_short_locale];
        if (locale_code) {
            return ajax.loadJS(gantt_path+'/codebase/locale/locale_'+locale_code+'.js');
        }
        return;
    },

    /**
     * This method ensure translatable tooltips message for tasks.
     */
    tooltipTask : function (start, end, event) {
        return "<b>" + _t("Task:") + "</b> " + event.text + "<br/><b>" + _t("Start date:") + "</b> " + this.tooltip_date_format(start) + "<br/><b>" + _t("End date:") + "</b> " + this.tooltip_date_format(end);
    },

});

});