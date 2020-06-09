odoo.define("web_celery.widgets", function (require) {
    var core = require("web.core");
    var _t = core._t;
    var Widget = require("web.Widget");

    var isOk = function (v) {
        return _.isNumber(v) && !_.isNaN(v);
    };

    /**
     * Base class that holds the state of a progress rendering bar.
     *
     * Properties:
     *
     * - title, a title for the progress bar.
     *
     * - message the current message to show in progress bar.
     *
     * - valuemin, valuemax and progress provide the minimal, maximal and
     *   current value.  Once set, valuemin and valuemax are not updated.
     *
     * - percent is automatically computed from the previous values.
     *
     * Invalid values are ignored.
     */
    var AbstractProgressBar = Widget.extend({
        init: function (parent) {
            this._super.apply(this, arguments);
            this.title = _t("Working");
            this.message = _t(
                "Your request is being processed (or about " +
                    "to be processed.)  Please wait."
            );
        },

        update: function (progress, valuemin, valuemax, message) {
            if (isOk(progress) && (!this.progress || this.progress < progress))
                this.progress = progress;
            // Once set, the valuemin and valuemax cannot be updated.
            if (isOk(valuemin) && !isOk(this.valuemin))
                this.valuemin = valuemin;
            if (isOk(valuemax) && !isOk(this.valuemax))
                this.valuemax = valuemax;
            if (
                isOk(this.progress) &&
                isOk(this.valuemax) &&
                isOk(this.valuemin)
            ) {
                var p = (this.percent = Math.round(
                    (this.progress / (this.valuemax - this.valuemin)) * 100
                ));
                if (p < 0 || p > 100) {
                    // Safely avoid any non-sensible value
                    this.progress = this.valuemin = this.valuemax = null;
                    this.percent = 0;
                }
            }
            this.message = message;
            this.trigger("progress_update", this);
        },
    });

    /**
     * A progress bar connected to a celery background job.
     *
     * Percent is automatically updated from the service 'web_celery'.  Sub
     * classes are required to provide the actual DOM.  Instances have
     * Deferred-like methods: then, fail, always, isResolved and isRejected.
     *
     */
    var CeleryProgressBar = AbstractProgressBar.extend({
        init: function (parent, job_uuid) {
            this._super.apply(this, arguments);
            this.job_uuid = job_uuid;
        },

        start: function () {
            // Only subscribe to events when the widget is visible.
            this.call(
                "web_celery",
                "attachJobNotification",
                this,
                this.job_uuid,
                this.on_job_notification
            );
            return $.when();
        },

        destroy: function () {
            this.call(
                "web_celery",
                "detachJobNotification",
                this,
                this.job_uuid,
                this.on_job_notification
            );
            this._super.apply(this, arguments);
        },

        on_job_notification: function (message) {
            var status = message.status;
            if (!status || status == "pending") {
                this.update(
                    message.progress,
                    message.valuemin,
                    message.valuemax,
                    message.message
                );
            }
        },
    });

    var BasicProgressBar = CeleryProgressBar.extend({
        xmlDependencies: ["/web_celery/static/src/xml/templates.xml"],
        template: "CeleryBasicProgressBar",

        custom_events: { progress_update: "on_progress_update" },

        on_progress_update: function () {
            if (this.message) {
                this.$(".message").text(this.message);
            }
            var $progressbar = this.$(".progress-bar");
            if (isOk(this.valuemin) && !$progressbar.attr("aria-valuemin")) {
                $progressbar.attr("aria-valuemin", this.valuemin);
            }
            if (isOk(this.valuemax) && !$progressbar.attr("aria-valuemax")) {
                $progressbar.attr("aria-valuemax", this.valuemax);
            }
            if (isOk(this.progress)) {
                $progressbar.attr("aria-valuenow", this.progress);
            }
            // percent should be always ok, but will show only a progress bar
            // if there's a progress value.
            if (isOk(this.percent) && isOk(this.progress)) {
                $progressbar.attr("style", "width: " + this.percent + "%");
                var $pmsg = $progressbar.find(".percent-message");
                if ($pmsg.length) {
                    $pmsg.text(this.percent + "%");
                } else {
                    var $msg = $progressbar.find(".progress-bar");
                    $msg.add(
                        '<span aria-hidden="true" class="percent-message">' +
                            this.percent +
                            "%</span>"
                    );
                }
            }
        },
    });

    var FullScreenProgressBar = BasicProgressBar.extend({
        xmlDependencies: ["/web_celery/static/src/xml/templates.xml"],
        template: "FullScreenProgressBar",
    });

    return {
        AbstractProgressBar: AbstractProgressBar,
        CeleryProgressBar: CeleryProgressBar,
        BasicProgressBar: BasicProgressBar,
        FullScreenProgressBar: FullScreenProgressBar,
    };
});

// Local Variables:
// indent-tabs-mode: nil
// End:
