odoo.define('web_celery.CeleryService', function (require) {
    "use strict";

    // That's 20 minutes!  This should account for the time in the queue plus
    // the running time.
    //
    var JOB_TIME_LIMIT = 1200000;

    var core = require('web.core'),
        Bus = require("web.Bus"),
        AbstractService = require('web.AbstractService'),
        widgets = require('web_celery.widgets'),
        concurrency = require("web.concurrency"),
        FullScreenProgressBar = widgets.FullScreenProgressBar;

    function getProgressChannel(job_uuid) {
        return 'celeryapp:' + job_uuid + ':progress';
    };

    var WebCeleryService = AbstractService.extend({
        init: function (parent) {
            this._super.apply(this, arguments);
            this.jobs = {};
            this.counter = 0;
            this.bus = new Bus();
        },

        start: function () {
            var res = this._super.apply(this, arguments);
            this.call('bus_service', 'onNotification', this, this._onNotification);
            return res;
        },

        appendBackgroundJob: function (action) {
            if (action.params.uuid) {
                var finished = this._addBackgroundJob(action.params.uuid, action.params.next_action);
                var tag = action.tag,
                    method = 'do_tag_' + tag;
                if (!!this[method]) {  // Call the do_tag_ methods (see below).
                    this[method].call(this, action.params, finished);
                }
                return finished.promise();
            };
            // This should not happen, but if it does, let's not hold the
            // action manager.
            return $.when();
        },

        attachJobNotification: function(obj, job_uuid, fn) {
            this.bus.on(getProgressChannel(job_uuid), obj, fn);
        },

        detachJobNotification: function(obj, job_uuid, fn) {
            this.bus.off(getProgressChannel(job_uuid), obj, fn);
        },

        _addBackgroundJob: function(job_uuid, next_action) {
            var result = $.Deferred();
            var timer = concurrency.delay(JOB_TIME_LIMIT);
            $.whichever(result, timer).then(function(which){
                if (which === timer) {
                    result.reject({
                        type: "warning",
                        kind: "timeout",
                    });
                }
            });
            var channel = getProgressChannel(job_uuid);
            this.call('bus_service', 'addChannel', channel);
            var self = this;
            result.always(function () {
                self.call("bus_service", "deleteChannel", channel);
            });
            // Register the current job so that the _onNotification knows
            // which deferred to signal.
            this.jobs[channel] = {finished: result, next_action: next_action};
            // TODO: Maybe move to the widgets.
            result.fail(function(failure_message){
                // Messages with 'kind' are *internal* of the Web Client, they
                // don't come from the server.
                if (!failure_message.hasOwnProperty("kind")) {
                    var error = {
                        message: failure_message.message.name,
                        data: failure_message.message
                    };
                    core.bus.trigger("rpc_error", error);
                }
            });
            // TODO: When we add the systray menu, this next_action must be
            // gone and replaced by an entirely different UI concept: many
            // parallel jobs can be running and any one of them (or several)
            // can finish at any time, we should not use the next_action (or
            // perform any action at all).  For the time being we do the same
            // we have done so far: reload if next_action is undefined or
            // perform the given next_action.
            result.then(function(success_message) {
                if (success_message.next_action) {
                    self.do_action(success_message.next_action);
                } else {
                    var controller = self.getParent().action_manager.getCurrentController();
                    if (controller && controller.widget && typeof(controller.widget.reload) == "function") {
                        controller.widget.reload();
                    } else {
                        self.do_action('reload');
                    }
                }
            });
            return result.promise();
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
                if (message.status === 'success') {
                    finished.resolve({
                        status: 'success',
                        next_action: message.result ? message.result : job.next_action
                    });
                    delete this.jobs[channel];
                } else if (message.status === 'failure') {
                    finished.reject({
                        status: 'failure',
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

        /**
         * Action tags
         */
        do_tag_block_no_progress: function(params, finished) {
            // By simply triggering rpc_request and rpc_response, we're using
            // the standard Loading mechanism of Odoo.
            //
            // I don't need to trigger the rpc_response_failed because the
            // WebCeleryService takes care of failures.
            core.bus.trigger('rpc_request');
            finished.always(function(){core.bus.trigger('rpc_response');});
        },

        do_tag_block_with_progress: function(params, finished) {
            var loading = new FullScreenProgressBar(this, params.uuid);
            loading.appendTo(this.getParent().$el);
            finished.always(function(){
                loading.destroy();
            });
        },
    });

    core.serviceRegistry.add('web_celery', WebCeleryService);

    return WebCeleryService;

});

// Local Variables:
// indent-tabs-mode: nil
// End:
