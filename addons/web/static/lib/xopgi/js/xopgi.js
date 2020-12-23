(function() {
    'use strict';

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
