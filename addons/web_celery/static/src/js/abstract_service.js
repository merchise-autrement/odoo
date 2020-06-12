odoo.define("web_celery.CeleryAbstractService", function (require) {
    "use strict";

    // That's 20 minutes!  This should account for the time in the queue plus
    // the running time.
    //
    var JOB_TIME_LIMIT = 1200000;

    var Bus = require("web.Bus"),
        AbstractService = require("web.AbstractService"),
        concurrency = require("web.concurrency");

    function getProgressChannel(job_uuid) {
        return "celeryapp:" + job_uuid + ":progress";
    }

    var CeleryAbstractService = AbstractService.extend({
        dependencies: ["bus_service"],

        init: function () {
            this._super.apply(this, arguments);
            this.jobs = {};
            this.bus = new Bus();
        },

        start: function () {
            var res = this._super.apply(this, arguments);
            this.call(
                "bus_service",
                "onNotification",
                this,
                this._onNotification
            );
            return res;
        },

        _onNotification: function (notifications) {
            var self = this;
            _.each(notifications, function (notification) {
                self._handleNotification(notification);
            });
        },

        _handleNotification: function (notification) {
            var channel = notification[0],
                message = notification[1];
            if (this.jobs.hasOwnProperty(channel)) {
                var job = this.jobs[channel],
                    finished = job.finished;
                if (message.status === "success") {
                    finished.resolve({
                        status: "success",
                        next_action: message.result
                            ? message.result
                            : job.next_action,
                    });
                    delete this.jobs[channel];
                } else if (message.status === "failure") {
                    finished.reject({
                        status: "failure",
                        traceback: message.traceback,
                        message: message.message,
                    });
                    delete this.jobs[channel];
                } else {
                    // This is normal progress message.
                    this.bus.trigger(channel, message);
                }
            }
        },

        appendBackgroundJob: function (action) {
            if (action.params.uuid) {
                var finished = this._addBackgroundJob(
                    action.params.uuid,
                    action.params.next_action
                );
                var tag = action.tag,
                    method = "do_tag_" + tag;
                var promise = finished.promise();
                if (!!this[method]) {
                    this[method].call(this, action.params, promise);
                }
                return promise;
            }
        },

        attachJobNotification: function (obj, job_uuid, fn) {
            this.bus.on(getProgressChannel(job_uuid), obj, fn);
        },

        detachJobNotification: function (obj, job_uuid, fn) {
            this.bus.off(getProgressChannel(job_uuid), obj, fn);
        },

        _addBackgroundJob: function (job_uuid, next_action) {
            var result = $.Deferred();
            var timer = concurrency.delay(JOB_TIME_LIMIT);
            $.whichever(result, timer).then(function (which) {
                if (which === timer) {
                    result.reject({
                        type: "warning",
                        kind: "timeout",
                    });
                }
            });
            var channel = getProgressChannel(job_uuid);
            this.call("bus_service", "addChannel", channel);
            var self = this;
            result.always(function () {
                self.call("bus_service", "deleteChannel", channel);
            });
            // Register the current job so that the _onNotification knows
            // which deferred to signal.
            this.jobs[channel] = {
                finished: result,
                next_action: next_action,
            };
            return result.promise();
        },
    });

    return CeleryAbstractService;
});
