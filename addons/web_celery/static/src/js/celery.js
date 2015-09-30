openerp.web_celery = function(instance){
    var pending_jobs = 0;

    instance.web.JobThrobber = instance.web.Throbber.extend({
        init: function(parent, options) {
            var uuid, next;
            this.uuid = uuid = options.params.uuid;
            this.next = options.params.next_action;
            this._super(parent);
            var bus;
            bus = this.bus = new instance.bus.Bus();
            bus.add_channel('celeryapp:' + uuid);
            bus.on('notification', this, this.on_job_notification);
            this.show();
            pending_jobs += 1;
        },

        show: function() {
            $.blockUI();
            instance.web.Throbber.throbbers.push(this);
            this.appendTo($(".oe_blockui_spin_container"));
        },

        start: function() {
            _.delay(_.bind(this.bus.start_polling, this.bus), 1);
            return this._super();
        },

        on_job_notification: function(){
            console.debug('Job', arguments);
            this.bus.stop_polling();
            if (!this.isDestroyed()) {
                if (this.next) {
                    var parent = this.getParent();
                    var self = this;
                    _.delay(function(){parent.do_action(self.next)}, 1);
                }
                this.destroy();
                $.unblockUI();
            }
        },

        destroy: function() {
            pending_jobs -= 1;
            this._super();
        }

    });

    instance.web.client_actions.add('wait_for_background_job',
                                    'instance.web.JobThrobber');
};
