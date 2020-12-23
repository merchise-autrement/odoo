odoo.define("web_celery.ActionManager", function (require) {
    "use strict";

    // Hooks the Odoo Action Manager to handle responses that should connect
    // with web_celery service.
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
