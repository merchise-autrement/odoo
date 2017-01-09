(function() {
    'use strict';

    // A deferred that resolves after a given `time` in milliseconds.  The
    // returned promise allows to postpone: Useful to implement the pattern of
    // waiting till completion but using checkpoints.
    $.elapsed = function(time, stopped) {
	var id;
	var res = $.Deferred();
	var main = function(){
            clearTimeout(id);
            res.resolve();
	};
	var postpone = function(_time) {
            clearTimeout(id);
            id = setTimeout(main, !!_time ? _time : time);
	};
	if (!stopped)
            id = setTimeout(main, time);
	var result = res.promise();
	result.postpone = postpone;
	result.start = postpone;
	return result;
    };

    // $.whichever(...promises); returns a promise that will be resolved
    // whenever any of its arguments resolves.
    $.whichever = function() {
	var res = $.Deferred();
	var defs = Array.prototype.slice.apply(arguments);
	defs.forEach(function (fn) {
	    $.when(fn).done(function(){ res.resolve(fn); })
                .fail(function(){ res.reject(fn); });
	});
	return res.promise();
    };

})();
