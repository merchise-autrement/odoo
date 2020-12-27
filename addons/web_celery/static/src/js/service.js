odoo.define("web_celery.CeleryService", function (require) {
    "use strict";

    const CeleryAbstractService = require("web_celery.CeleryAbstractService");
    const core = require("web.core"),
          widgets = require("web_celery.widgets"),
          FullScreenProgressBar = widgets.FullScreenProgressBar;

    // Use the root widget to be able to print the fullscreen progress bar.
    const root = require('root.widget');

    /**
     * A service for the background celery jobs in the Web Client.
     *
     * @extends CeleryAbstractService
     *
     * This service connects the server's background jobs responses of
     * WAIT_FOR_TASK and QUIETLY_WAIT_FOR_TASK with WebClient's UI.
     *
     * WAIT_FOR_TASK creates a full-screen progress bar that shows the progress
     * of the background job.  This type of response can be cancelled.
     *
     * QUIETLY_WAIT_FOR_TASK locks the screen with the default RPC spinner,
     * instead of waiting for an AJAX response we're waiting for the background
     * job.
     *
     */
    const WebCeleryService = CeleryAbstractService.extend({
        appendBackgroundJob: function () {
            this._super.apply(this, arguments);
            // This should not happen, but if it does, let's not hold the
            // action manager.
            return $.when();
        },

        _addBackgroundJob: function () {
            var result = this._super.apply(this, arguments);
            // TODO: Maybe move to the widgets.
            result.fail(function (failure_message) {
                // Messages with 'kind' are *internal* of the Web Client, they
                // don't come from the server.
                if (!failure_message.hasOwnProperty("kind")) {
                    var error = {
                        message: failure_message.message.name,
                        data: failure_message.message,
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
            var self = this;
            result.then(function (success_message) {
                if (success_message.next_action) {
                    self.do_action(success_message.next_action);
                } else {
                    var controller = root.action_manager.getCurrentController();
                    if (
                        controller &&
                        controller.widget &&
                        typeof controller.widget.reload == "function"
                    ) {
                        controller.widget.reload();
                    } else {
                        self.do_action("reload");
                    }
                }
            });
            return result;
        },

        do_tag_block_no_progress: function (_params, finished) {
            // By simply triggering rpc_request and rpc_response, we're using
            // the standard Loading mechanism of Odoo.
            //
            // I don't need to trigger the rpc_response_failed because the
            // WebCeleryService takes care of failures.
            core.bus.trigger("rpc_request");
            finished.always(function () {
                core.bus.trigger("rpc_response");
            });
        },

        do_tag_block_with_progress: function (params, finished) {
            var loading = new FullScreenProgressBar(
                this,
                params.uuid,
                params.cancellable
            );
            loading.appendTo(root.$el);
            finished.always(function () {
                loading.destroy();
            });
        },
    });

    core.serviceRegistry.add("web_celery", WebCeleryService);
    return WebCeleryService;
});

// Local Variables:
// indent-tabs-mode: nil
// tab-width: 4
// js-indent-level: 4
// End:
