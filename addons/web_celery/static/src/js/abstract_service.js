odoo.define("web_celery.CeleryAbstractService", function (require) {
    "use strict";

    // That's 20 minutes!  This should account for the time in the queue plus
    // the running time.
    //
    var JOB_TIME_LIMIT = 1200000;

    var Bus = require("web.Bus"),
        AbstractService = require("web.AbstractService"),
        concurrency = require("web.concurrency");

    var CSRF_TOKEN = require("web.core").csrf_token;
    var session = require("web.session");

    function getProgressChannel(job_uuid) {
        return "celeryapp:" + job_uuid + ":progress";
    }

    /**
     * Basic implementation of the celery service.
     *
     * This services coordinates the background jobs with the UI and the rest of
     * the system.  The abstract service merely connects with the server to get
     * updates from the background jobs currently running and dispatch
     * notifications.
     */
    var CeleryAbstractService = AbstractService.extend({
        dependencies: ["bus_service"],

        init: function () {
            this._super.apply(this, arguments);
            this.jobs = {};
            this.bus = new Bus();
        },

        /**
         * Connects to the bus service so that we can receive notifications from
         * the server.
         */
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
                } else if (message.status === "failure") {
                    finished.reject({
                        status: "failure",
                        traceback: message.traceback,
                        message: message.message,
                    });
                } else if (message.status === "cancelled") {
                    // We're resolving the deferred without a next_action.
                    // The next_action is only sensible when the job actually
                    // finishes.
                    finished.resolve({
                        status: "cancelled",
                    });
                } else {
                    // This is normal progress message.
                    this.bus.trigger(channel, message);
                }
            }
        },

        /**
         * Issue a request to cancel a background job.
         *
         * If the background job is not cancellable, nothing happens.  If the
         * request to the server doesn't fail we assume the job will be
         * cancelled and resolve the job's status (which may affect the UI).
         * Further notifications from the server regarding a job which we
         * cancelled are ignored (unless forced is true).
         *
         * @param {UID} job_uuid The background job UID.
         * @param {boolean} forced  Force the cancellation of the background job.
         *
         */
        cancelBackgroundJob: function (job_uuid, forced) {
            var channel = getProgressChannel(job_uuid);
            if (this.jobs.hasOwnProperty(channel)) {
                var job = this.jobs[channel];
                if (job.cancellable || forced) {
                    session
                        .rpc("/web_celery/!cancel/" + job_uuid, {
                            csrf_token: CSRF_TOKEN,
                        })
                        .then(function () {
                            // The most likely scenario is that we get the Terminated
                            // error from the server before getting the cancelled
                            // notification, so let's signal the cancellation
                            // ourselves.
                            job.finished.resolve({ status: "cancelled" });
                        });
                }
            }
        },

        /**
         * Track a new background job.
         *
         * You should call this when the server responds it has issued a new
         * background job and you want to track its status/progress.
         *
         * @param {Object} action The background job action-like record.
         *
         * @param {UID} action.uuid  The background job identifier.  This is
         *        used to keep track and know about the status of the background
         *        job.
         *
         * @param {Object|null} action.next_action  An object describing the
         *        next action to execute once the background jobs finish
         *        sucessfully. This is ignored if the 'sucess' status
         *        notification contains a next action.
         *
         * @param {boolean} action.cancellable  Whether this background job can
         *        be cancelled.
         *
         * @param {str|null} action.tag  If the action has a tag run the
         *        service's code that to process the tag.  See {@link WebCeleryService}.
         *
         */
        appendBackgroundJob: function (action) {
            if (action.params.uuid) {
                var finished = this._addBackgroundJob(
                    action.params.uuid,
                    action.params.next_action,
                    action.params.cancellable
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

        /**
         * Register a callback to get notifications from the background job.
         *
         * @param {Object} obj The object that is `this` when running the function `fn`.
         * @param {UID} job_uuid The job UID
         * @param {Function} fn The callback function
         */
        attachJobNotification: function (obj, job_uuid, fn) {
            this.bus.on(getProgressChannel(job_uuid), obj, fn);
        },

        /**
         * Unregister a notification callback for the background job.
         *
         * @param {Object} obj The active object registered to get notifications.
         * @param {UID} job_uuid The job UID
         * @param {Function} fn The callback function
         */
        detachJobNotification: function (obj, job_uuid, fn) {
            this.bus.off(getProgressChannel(job_uuid), obj, fn);
        },

        /**
         * Send a cancel request to all background jobs.
         *
         */
        cancelPendingJobs: function () {
            console.info("Cancelling pending jobs", this.jobs);
            _.each(
                this.jobs,
                function (job) {
                    this.cancelBackgroundJob(job.uuid, true);
                },
                this
            );
        },

        _addBackgroundJob: function (job_uuid, next_action, cancellable) {
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
                delete self.jobs[channel];
            });
            // Register the current job so that the _onNotification knows
            // which deferred to signal.
            this.jobs[channel] = {
                uuid: job_uuid,
                finished: result,
                next_action: next_action,
                cancellable: cancellable,
            };
            return result.promise();
        },
    });

    return CeleryAbstractService;
});
