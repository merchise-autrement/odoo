odoo.define("web_celery.CeleryService", function (require) {
    "use strict";

    var CeleryAbstractService = require("web_celery.CeleryAbstractService");
    var core = require("web.core"),
        widgets = require("web_celery.widgets"),
        FullScreenProgressBar = widgets.FullScreenProgressBar;

    var WebCeleryService = CeleryAbstractService.extend({
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
                    var controller = self
                        .getParent()
                        .action_manager.getCurrentController();
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
            var loading = new FullScreenProgressBar(this, params.uuid);
            loading.appendTo(this.getParent().$el);
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
// End:
