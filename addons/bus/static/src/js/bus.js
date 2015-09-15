(function() {
    var bus = openerp.bus = {};

    // Return a promise that will be resolved when the page becomes visible.
    var page_visible = function() {
        var res = $.Deferred();
        var check_hidden = function(){
            // The !! serves the purpose of both having the value of `hidden`
            // and detecting if that value is present at all (older browsers
            // don't have it).  If the browser supports the visibility API
            // we'll get the true value of `hidden`, if not, we'll get false
            // as if the page is always visible.
            var hidden = !!document.hidden;
            if (!hidden){
                res.resolve();
                $(document).off('visibilitychange', check_hidden);
            }
            return hidden;
        }
        var hidden = check_hidden();
        if (hidden)
            $(document).on('visibilitychange', check_hidden);
        return res.promise();
    }


    bus.HIDDEN_DELAY = 4000;
    bus.ERROR_DELAY = 10000;

    var rolldice = function() {
        return Math.floor((Math.random()*20)+1)*1000;
    }

    bus.Bus = openerp.Widget.extend({
        init: function(){
            this._super();
            this.options = {};
            this.activated = false;
            this.channels = [];
            this.last = 0;
            this.stop = false;
        },
        start_polling: function(){
            if(!this.activated){
                this.poll();
                this.stop = false;
            }
        },
        stop_polling: function(){
            this.activated = false;
            this.stop = true;
            this.channels = [];
        },
        poll: function() {
            var self = this;
            self.activated = true;
            var data = {'channels': self.channels, 'last': self.last, 'options' : self.options};
            var poll = _.bind(self.poll, self);
            openerp.session.rpc(
                '/longpolling/poll',
                data, {shadow : true}
            ).then(function(result) {
                _.each(result, _.bind(self.on_notification, self));
                if(!self.stop){
                    // Poll when either HIDDEN_DELAY has passed or the page
                    // becomes visible, if the page is already visible the
                    // poll will be done immediately.
                    var timer = $.elapsed(bus.HIDDEN_DELAY + rolldice());
                    var visible = page_visible();
                    $.whichever(timer, visible).done(function(){
                        poll();
                    });
                }
            }, function(unused, e) {
                // no error popup if request is interrupted or fails for any reason
                e.preventDefault();
                // random delay to avoid massive longpolling
                setTimeout(poll, bus.ERROR_DELAY + rolldice());
            });
        },
        on_notification: function(notification) {
            if (notification.id > this.last) {
                this.last = notification.id;
            }
            this.trigger("notification", [notification.channel, notification.message]);
        },
        add_channel: function(channel){
            if(!_.contains(this.channels, channel)){
                this.channels.push(channel);
            }
        },
        delete_channel: function(channel){
            this.channels = _.without(this.channels, channel);
        },
    });

    // singleton
    bus.bus = new bus.Bus();
    return bus;
})();


// Local Variables:
// indent-tabs-mode: nil
// End:
