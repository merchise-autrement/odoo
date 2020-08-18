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
     * - valuemin, valuemax and progress provide the minimal, maximal and
     *   current value.  Once set, valuemin and valuemax are not updated.
     *
     * - percent is automatically computed from the previous values.
     *
     * Invalid values are ignored.
     */
    var AbstractProgressBar = Widget.extend({
        /**
         * Update the internal state of the progress bar.  Triggers the event
         * 'progress_update' so that the UI could reflect the changes.
         *
         * @param {int|float} progress The progress value which should be
         *                             between `valuemin` and `valuemax`
         * @param {int|float} valuemin The minimal value of the progress
         * @param {int|float} valuemax The maximal value of the progress
         */
        update: function (progress, valuemin, valuemax) {
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
            this.trigger("progress_update", this);
        },

        forceCompletion: function () {
            if (isOk(this.valuemax)) {
                this.update(this.valuemax);
            } else {
                this.progress = null;
                this.update(1, 0, 1);
            }
        },
    });

    /**
     * A basic progress bar widget.
     *
     * The default template shows a progress in ARIA progressbar:
     *
     *     | . . . . 20%  . . . . .'           |
     *
     */
    var BasicProgressBar = AbstractProgressBar.extend({
        xmlDependencies: ["/web_celery/static/src/xml/templates.xml"],
        template: "ProgressBar",
        custom_events: { progress_update: "on_progress_update" },

        on_progress_update: function () {
            var $progressbar = this.$el.find(".progress-bar");
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

    /**
     * A progress bar which takes control of the entire document.
     */
    var FullScreenProgressBar = BasicProgressBar.extend({
        xmlDependencies: ["/web_celery/static/src/xml/templates.xml"],
        template: "FullScreenProgressBar",
    });

    /**
     * Mixin to create a coordinated (staged) set of progress bars, adding a
     * title, message, and Celery service-related capabilities.  Every {@link
     * BasicProgressBar} progress is updated individually.
     */
    var CeleryProgressBarMixin = {
        events: {
            "click button[name='cancel']": "cancel",
        },
        celery_service: "web_celery",

        init: function (job_uuid, cancellable, stages) {
            this.stages = stages
                ? stages
                : [["", 1, "web-celery-progress-stage-0"]];
            this._progress_bars = {};
            this._pending_stages_index = _.map(
                this.stages,
                (stage) => stage[0]
            );
            this.job_uuid = job_uuid;
            this.cancellable = cancellable;
            this.title = _t("Working");
            this.message = _t(
                "Your request is being processed (or about to be processed.)  Please wait."
            );
        },

        getProgressBarByStage: function (stage_name) {
            return this._progress_bars[stage_name ? stage_name : ""];
        },

        renderStages: function () {
            var self = this;
            var staged_progress_bars = this.$el.find(
                "div.staged-progress-bars"
            );
            var grid_template_columns = "";
            self.stages.forEach(function (stage_info) {
                var stage_name = stage_info[0] ? stage_info[0] : "";
                var size_fraction = stage_info[1];
                var css_class = stage_info[2];
                var div = $(
                    "<div class='" +
                        css_class +
                        " stage-" +
                        stage_name +
                        "'></div>"
                );
                var basic_progress_bar = new BasicProgressBar(self);
                basic_progress_bar.appendTo(div);
                div.appendTo(staged_progress_bars);
                self._progress_bars[stage_name] = basic_progress_bar;
                if (!grid_template_columns) {
                    grid_template_columns = size_fraction + "fr";
                } else {
                    grid_template_columns += " " + size_fraction + "fr";
                }
            });
            staged_progress_bars.css(
                "grid-template-columns",
                grid_template_columns
            );
        },

        /**
         * Cancel the background job.
         */
        cancel: function () {
            this.call(
                this.celery_service,
                "cancelBackgroundJob",
                this.job_uuid
            );
        },

        /**
         * Attach the widget to the celery service so that it can
         * track the progress and status of the background job.
         */
        start: function () {
            this.renderStages();
            // Only subscribe to events when the widget is visible.
            this.call(
                this.celery_service,
                "attachJobNotification",
                this,
                this.job_uuid,
                this.on_job_notification
            );
        },

        destroy: function () {
            this.call(
                this.celery_service,
                "detachJobNotification",
                this,
                this.job_uuid,
                this.on_job_notification
            );
        },

        /**
         * Handle the status/progress notification from the background job.
         *
         * The `message.status` can be 'pending', 'success', 'failure', or
         * 'cancelled'.
         *
         * If it's 'pending', the `message` payload is the progress data.  See
         * the `update` method.
         *
         * @param {Object} message The message comming from the background job
         */
        on_job_notification: function (message) {
            var status = message.status;
            if (!status || status == "pending") {
                this._updatePengingStages(message.stage);
                var progress_bar = this.getProgressBarByStage(message.stage);
                if (progress_bar) {
                    progress_bar.update(
                        message.progress,
                        message.valuemin,
                        message.valuemax
                    );
                    if (message.progress == message.valuemax) {
                        this.$el
                            .find(".stage-" + message.stage)
                            .addClass("stage-done");
                        progress_bar.forceCompletion();
                        // message.stage is the first in the array because of
                        // what we do in _updatePendingStages
                        this._pending_stages_index.shift();
                    }
                }
                if (message.message) {
                    this.showMessage(message.message);
                }
            }
        },

        showMessage: function (message) {
            this.$el.find("p.message").text(message);
        },

        _updatePengingStages: function (stage) {
            var idx = this._pending_stages_index.indexOf(stage);
            if (idx !== -1) {
                var previous = this._pending_stages_index.slice(0, idx);
                for (const stage of previous) {
                    this.forceStagedBarCompletion(stage);
                }
                this._pending_stages_index.splice(0, idx);
            }
        },

        forceStagedBarCompletion: function (stage) {
            var progress_bar = this.getProgressBarByStage(stage);
            if (progress_bar) {
                progress_bar.forceCompletion();
            }
        },
    };

    var FullScreenCeleryProgressBar = FullScreenProgressBar.extend(
        CeleryProgressBarMixin,
        {
            init: function (_parent, job_uuid, cancellable, stages) {
                this._super.apply(this, arguments);
                CeleryProgressBarMixin.init.call(
                    this,
                    job_uuid,
                    cancellable,
                    stages
                );
            },

            start: function () {
                CeleryProgressBarMixin.start.call(this);
                return this._super.apply(this, arguments);
            },

            destroy: function () {
                CeleryProgressBarMixin.destroy.call(this);
                return this._super.apply(this, arguments);
            },
        }
    );

    return {
        AbstractProgressBar: AbstractProgressBar,
        BasicProgressBar: BasicProgressBar,
        FullScreenProgressBar: FullScreenProgressBar,
        CeleryProgressBarMixin: CeleryProgressBarMixin,
        FullScreenCeleryProgressBar: FullScreenCeleryProgressBar,
    };
});

// Local Variables:
// indent-tabs-mode: nil
// End:
