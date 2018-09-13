odoo.define('web_gantt.GanttModel', function (require) {
"use strict";

var core = require('web.core');
var AbstractModel = require('web.AbstractModel');

var _t = core._t;

var OdooDateFormat = 'YYYY-MM-DD HH:mm:ss';

return AbstractModel.extend({
    /**
     * @override
     * @param {Widget} parent
     */
    init: function () {
        this._super.apply(this, arguments);
    },

    /**
     * @override
     * @param {any} params
     * @returns {Deferred}
     */
    load: function (params) {
        var groupBy = params.groupBy;
        this.localData = Object.create(null);
        this.fields = params.fields;
        this.mapping = params.mapping;
        this.groupBy = groupBy;
        this.modelName = params.modelName;
        this.parent_tasks = [];
        this.links_field = params.links;
        if (this.links_field){
            var rel_field = this.fields[this.links_field];
            var mappingLinks = _.omit(params.links_options, 'types');
            var needed = {
                source: rel_field.relation_field,
                id:'id',
                lag: 'lag',
                display_name: 'display_name'
            };
            this.mappingLinks = _.extend(needed, mappingLinks);
            this.linkModel = rel_field.relation;
        }
        this.gantt = {
            data: [],
            fieldNames:params.fieldNames,
            groupBy: groupBy,
            domain: params.domain,
            context: params.context,
        };
        return this._loadGantt(params.res_ids);
    },

    /**
     * @override
     * @returns {Object}
     */
    get: function (id, params) {
        if (id){
            return this.localData[id];
        }
        return _.extend({}, {
            fields: this.fields,
            gantt: this.gantt
        });
    },

    /**
     * @private
     * @returns {Deferred}
     */
    _loadGantt: function (ids) {
        var self = this;
        // the method 'search_read' could be used but it does a read with
        // '_classic_read' load. In this case to ensure that gantt data
        // are properly created, only ids are used as fields values.
        return this._getIds(ids).then(function (ids) {
            return self._rpc({
                model: self.modelName,
                method: 'read',
                context: self.gantt.context,
                args : [ids, self.gantt.fieldNames, 'no_classic_read'],
            });
        }).then(function (events) {
            return self.on_data_loaded(events);
        }).then(function(events){
            return self.get_links(events);
        });
    },

    _getIds: function(ids){
        if (!ids){
            return this._rpc({
                model: this.modelName,
                method: 'search',
                context: this.gantt.context,
                args: [this.gantt.domain],
            });
        }
        else {
            var deferred = $.Deferred();
            return deferred.resolve(ids);
        }
    },

    /**
     * @private
     * Process all tasks for gantt use
     */
    on_data_loaded: function (data) {
        var preload_def = $.Deferred();
        var self = this;
        var links = [];
        var records = _.map(data, function (record) {
            var task = self.recordToTask(record);
            var localRec = _.extend(record, task, {res_id: task.id});
            self.localData[localRec['id']] = localRec;
            return localRec;
        });
        this.gantt.data['data'] = records;
        return preload_def.resolve(records);
    },

    /**
     * @private
     *
     * @returns {Deferred} Links of all tasks
     */
    get_links: function(data){
        if (this.links_field){
            var self = this;
            var link_ids = [];
            _.each(data, function(d){
                link_ids = _.union(link_ids, d[self.links_field]);
            });
            if (link_ids){
                return this._rpc({
                    model: this.linkModel,
                    method: 'read',
                    context: self.gantt.context,
                    args : [link_ids, [], 'no_classic_read'],
                }).then(function(data){
                    self.on_links_loaded(data);
                });
            }
        }
    },

    /**
     * @private
     *
     * Process all links for gantt use.
     */
    on_links_loaded: function(records){
        var self = this;
        var links = _.map(records, function(record){
            return self.recordToLink(record);
        });
        self.gantt.data['links'] = links;
    },

    /**
     * @override
     * @param {any} id
     * @param {any} params
     * @returns {Deferred}
     */
    reload: function (id, params) {
        if (params.domain) {
            this.gantt.domain = params.domain;
        }
        return this._loadGantt();
    },

    /**
     * Convert a gantt task to an odoo record.
     */
    taskToRecord: function(task){
        var self = this;
        var record = {};
        _.each(this.mapping, function(recordKey, ganttKey){
            var val = task[ganttKey];
            if (val instanceof Date){
                val = self.dateToStr(val);
            }
            record[recordKey] = val;
        });
        return record;
    },

    /**
     * Convert an odoo record to a gantt task.
     */
    recordToTask: function(record){
        var self = this;
        var task = {};
        _.each(self.mapping, function(recordKey, ganttKey){
            task[ganttKey] = record[recordKey];
            if (ganttKey === 'parent' && record[recordKey]){
                if (!_.contains(self.parent_tasks, record[recordKey]))
                    self.parent_tasks.push(record[recordKey]);
            }
        });
        return task;
    },

    /**
     * Convert a gantt link to an odoo record.
     */
    linkToRecord: function(link){
        var self = this;
        var record = {};
        _.each(this.mappingLinks, function(recordKey, linkKey){
            if (link[linkKey] !== undefined){
                record[recordKey] = link[linkKey];
            }
            //in links, lag could be represented as 'lag' or 'lead' key
            else if (linkKey === 'lag' && link['lead']){
                record[recordKey] = link['lead'];
            }
        });
        return record;
    },

    /**
     * Convert an odoo record to a gantt link.
     */
    recordToLink: function(record){
        var self = this;
        var link = {};
        _.each(this.mappingLinks, function(recordKey, linkKey){
            if (record[recordKey] !== undefined){
                if (linkKey === 'lag'){
                    var lag = record[recordKey];
                    linkKey = (lag >= 0) ? 'lag' : 'lead';
                }
                link[linkKey] = record[recordKey];
            }
        });
        return link;
    },

    /**
     * Update task values on server.
     */
    saveTask: function(task){
        var record = this.taskToRecord(task);
        var values = _.omit(record, ['id', 'duration','display_name']);
        return this._rpc({
                model: this.modelName,
                method: 'write',
                context: this.gantt.context,
                args : [task.id, values],
        }).then(function(result){
            return;
        });
    },

    /**
     * Convert Date in utc to a string date in utc, useful on server operations.
     */
    dateToStr: function (value) {
        var val = moment.utc(value);
        return val.format(OdooDateFormat);
    },

    /**
     * If a link type is a valid type.
     */
    isValidType: function(value){
        var values = _.values(gantt.config.links);
        return (value in values);
    },

    /**
     * Update link values on server.
     */
    saveLink: function(link){
        var args = [];
        if (link.$new){
            var method = 'create';
        }
        else{
            var method = 'write';
            args.push(link.id);
        }
        var record = this.linkToRecord(link);
        var values = _.omit(record, ['id','display_name']);
        args.push(values);
        return this._rpc({
                model: this.linkModel,
                method: method,
                context: this.gantt.context,
                args : args,
        }).then(function(result){
            return;
        }).fail(function(error){
            gantt.deleteLink(link.id);
        });
    },

    /**
     * Delete link on server.
     */
    deleteLink: function(link){
        var self = this;
        if(!link.$new){
            return this._rpc({
                model: this.linkModel,
                method: 'unlink',
                context: this.gantt.context,
                args : [link.id],
            }).then(function(result){
                return;
            }).fail(function(error){
                gantt.message({type:"error", text:"Something went wrong."});
                self.reload();
            });
        }
        return;
    },
});

});