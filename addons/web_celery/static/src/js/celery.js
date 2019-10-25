odoo.define('web_celery', function(require){
    // TODO: Move to a service?
    var pending_jobs = 0;

    var AbstractAction = require('web.AbstractAction');

    var core = require('web.core');
    var _t = core._t;
    var framework = require('web.framework');
    var CrashManager = require('web.CrashManager');
    var concurrency = require('web.concurrency');
    var delay = concurrency.delay;

    // That's 20 minutes!  This should account for the time in the queue plus
    // the running time.
    var JOB_TIME_LIMIT = 1200000;

    var get_progress_channel = function(job) {
        return 'celeryapp:' + job.uuid + ':progress';
    };

    var isOk = function(v) {return _.isNumber(v) && !_.isNaN(v);};

    var JobThrobber = AbstractAction.extend({
        xmlDependencies: [],

        canBeRemoved: function(){
            // We can be removed after the job is either done or failed, but
            // not before.  We won't hold the controller hostage if the job
            // failed.
            var res = $.Deferred();
            this.finished.done(function(){res.resolve()}).fail(function(){res.resolve()});
            return res.promise();
        },

        on_attach_callback: function() {
            this.start_waiting();
        },

        init: function(parent, action, options) {
            var res = this._super.apply(this, arguments);
            this.uuid = action.params.uuid;
            this.title = _t('Working');
            this.message = _t('Your request is being processed (or about '+
                              'to be processed.)  Please wait.');
            this.channel = get_progress_channel(action.params);
            this.finished = $.Deferred();
        },

        willStart: function() {
            console.debug('willStart', arguments);
            var self = this;
            var res = this._super.apply(this, arguments);
            res.done(function(){
                self.call('bus_service', 'addChannel', self.channel);
                self.call('bus_service', 'onNotification', self,
                          self.on_job_notification);
                pending_jobs += 1;
                $.when(self.finished)
                    .done(function(message){
                        self.show_success(message);
                    })
                    .fail(function(message){
                        self.show_failure(message);
                    });
            });
            return res;
        },

        update: function(progress, valuemin, valuemax, message) {
            if (isOk(progress) && (!this.progress || this.progress < progress))
                this.progress = progress;
            // Once set, the valuemin and valuemax cannot be updated.
            if (isOk(valuemin) && !isOk(this.valuemin))
                this.valuemin = valuemin;
            if (isOk(valuemax) && !isOk(this.valuemax))
                this.valuemax = valuemax;
            if (isOk(this.progress) && isOk(this.valuemax) && isOk(this.valuemin)) {
                var p = this.percent = Math.round(this.progress/(this.valuemax-this.valuemin)*100);
                if (p < 0 || p > 100) {
                    // Safely avoid any non-sensible value
                    this.progress = this.valuemin = this.valuemax = null;
                    this.percent = 0;
                }
            }
            this.message = message;
            this.updateView();
        },

        on_job_notification: function(notifications){
            console.debug('Celery job notifications', notifications);
            var self = this;
            _.each(notifications, function (params) {
                var channel = params[0];
                if (channel != self.channel)
                    return;
                var message = params[1];
                var status = message.status;
                if (status && (status == 'success' || status == 'failure')) {
                    if (status != 'failure') {
                        self.finished.resolve(message);
                    }
                    else {
                        self.finished.reject(message);
                    }
                } else {
                    self.update(message.progress, message.valuemin,
                        message.valuemax, message.message);
                }
            });
        },

        start_waiting: function() {
            var timer = delay(JOB_TIME_LIMIT);
            var finished = this.finished;
            var self = this;
            $.whichever(finished, timer).always(function(which){
                if (which == timer) {
                    finished.reject({
                        type: "warning",
                        kind: "timeout"
                    });
                }
                self.stop_waiting();
            });
        },

        stop_waiting: function() {
            this.call('bus_service', 'deleteChannel', this.channel);
            this.finished.resolve();
        },

        destroy: function() {
            console.trace('Destroying');
            pending_jobs -= 1;
            this._super.apply(this, arguments);
        },

        show_failure: function() { },

        show_success: function() { },

        updateView: function() { },

    });

    var FailureSuccessReporting = JobThrobber.extend({
        do_close: function(){
            var self = this;
            _.defer(function(){
                self.trigger_up('history_back');
                self.destroy();
                self.trigger_up('reload');
            });
        },

        do_close_with_action: function(action){
            var self = this;
            _.defer(function(){
                var parent = self.getParent();
                var controller = parent.controllerStack.pop();
                self.trigger_up('history_back');
                self.do_action(action);
                self.destroy();
                parent._removeControllers([controller]);
            });
        },

        show_success: function(message) {
            var next_action = message.result,
                parent = this.getParent(),
                self = this;
            if (!!next_action) {
                this.do_close_with_action(next_action);
            } else {
                this.do_close();
            }
        },

        show_failure: function(message) {
            // TODO: Verify the failure
            if (!!message.kind) {
                this.do_warn(
                    _t('Ask for help'),
                    _t("You're stuck waiting for a job that is taking "+
                       "forever.  Grab the next IT guy and ask help."),
                    true
                );
            }
            else {
                var error = message;
                var data = error.data = _.clone(message.message);
                // We need to copy the 'message' title of the error.
                if (!!data.message) {
                    error.message = data.message;
                }
                core.bus.trigger('rpc_error', error);
            }
            this.do_close();
        }
    });

    var ProgressBarThrobber = FailureSuccessReporting.extend({
        xmlDependencies: ['/web_celery/static/src/xml/templates.xml'],
        template: "BackgroundJobProgress",

        on_attach_callback: function() {
            this._super.apply(this, arguments);
            this.$el.modal('show');
        },

        on_detach_callback: function() {
            this._super.apply(this, arguments);
            this.$el.modal('hide');
        },

        updateView: function() {
            if (this.message) {
                this.$('.message').text(this.message);
            }
            var $progressbar = this.$('.progress-bar');
            if (isOk(this.valuemin) && !$progressbar.attr('aria-valuemin')) {
                $progressbar.attr('aria-valuemin', this.valuemin);
            }
            if (isOk(this.valuemax) && !$progressbar.attr('aria-valuemax')) {
                $progressbar.attr('aria-valuemax', this.valuemax);
            }
            if (isOk(this.progress)) {
                $progressbar.attr('aria-valuenow', this.progress);
            }
            // percent should be always ok, but will show only a progress bar
            // if there's a progress value.
            if (isOk(this.percent) && isOk(this.progress)) {
                $progressbar.attr('style', 'width: ' + this.percent + '%');
                var $pmsg = $progressbar.find('.percent-message');
                if ($pmsg.length){
                    $pmsg.text(this.percent + '%');
                } else {
                    $msg = $progressbar.find('.progress-bar');
                    $msg.add('<span aria-hidden="true" class="percent-message">' +
                             this.percent + '%</span>');
                }
            }
        },

        destroy: function() {
            // For some reason, when showing the dialog two backdrops are
            // being placed in the DOM, but hiding only removes one: remove
            // them all.
            this.$el.on('hide.bs.modal', function() {
                $('body .modal-backdrop.in').detach();
            });
            this.$el.modal('hide');
            this._super.apply(this, arguments);
        }
    });

    var SpinnerThrobber = FailureSuccessReporting.extend({
        SPINNER_WAIT: 250,
        xmlDependencies: ['/web_celery/static/src/xml/templates.xml'],

        start_waiting: function() {
            this._super.apply(this, arguments);
            this.active = false;
            // Wait at most 250ms (asumming the default value of SPINNER_WAIT)
            // to show the spinner.  If the job does not send any report, the
            // spinner will be showed after this amount of time.  If the job
            // sends a report before 250ms (which is rare) the spinner will
            // show at that moment.
            _.delay(_.bind(this.updateView, this), this.SPINNER_WAIT);
        },

        updateView: function() {
            if (!this.active) {
                framework.blockUI();
                this.active = true;
            }
        },

        show_success: function() {
            if (this.active) {
                framework.unblockUI();
                this.active = false;
            }
            this._super.apply(this, arguments);
        },

        show_failure: function() {
            if (this.active) {
                framework.unblockUI();
                this.active = false;
            }
            this._super.apply(this, arguments);
        }

    });

    core.action_registry.add('wait_for_background_job', ProgressBarThrobber);
    core.action_registry.add('quietly_wait_for_background_job', SpinnerThrobber);

    return {
        JobThrobber: JobThrobber,
        FailureSuccessReporting: FailureSuccessReporting,
        ProgressBarThrobber: ProgressBarThrobber,
        SpinnerThrobber: SpinnerThrobber
    };
});

// Local Variables:
// indent-tabs-mode: nil
// End:
