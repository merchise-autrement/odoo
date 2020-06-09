odoo.define("web_celery.ActionManager", function (require) {
    "use strict";

    /**
     * Hooks the Odoo Action Manager to handle the following client responses:
     *
     * `wait_for_background_job`
     *
     *   The client action for waiting for a background job to complete.
     *
     * `quietly_wait_for_background_job`
     *
     *   The client action that waits quietly for a background job to
     *   complete.  In this context *quietly* means just displaying the usual
     *   AJAX spinner.
     *
     * `wait_for_background_job_in_systray`
     *
     *   The client action that
     *
     */
    var ActionManager = require("web.ActionManager");
    ActionManager.include({
        _handleAction: function (action, options) {
            if (action.type == "web.celery.background_job") {
                return this.call(
                    "web_celery",
                    "appendBackgroundJob",
                    action,
                    options
                );
            }
            return this._super.apply(this, arguments);
        },
    });
});

// Local Variables:
// indent-tabs-mode: nil
// End:
