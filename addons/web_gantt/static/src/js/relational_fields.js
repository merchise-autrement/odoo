odoo.define('web_gantt.relational_fields', function(require){
"use strict";

    var relational_fields = require('web.relational_fields')
    var FieldX2Many = relational_fields.FieldX2Many;
    var GanttView = require('web_gantt.GanttView');
    var GanttRenderer= require('web_gantt.GanttRenderer');

    FieldX2Many.include({
        /**
         * Instanciates gantt renderer if needed.
         *
         * @override
         * @private
         * @returns {Deferred|undefined}
         */
        _render: function () {
            var self = this;
            if (this.renderer || !this.view)
                return this._super();
            if (this.view){
                var arch = this.view.arch;
                if (arch.tag !== 'gantt')
                    return this._super();
                else{
                    var viewType = 'gantt';
                    var options = _.extend(this.value,{
                        modelName:this.value.model,
                        model:this.value.model,
                        ids: this.value.res_ids,
                    });
                    this.view.arch.attrs = _.extend(arch.attrs, {x2manyField:true});
                    var ganttView = new GanttView(this.view,options);
                    var self = this;
                    return ganttView.getController(this).then(function(controller){
                        self.renderer = controller.renderer;
                        self.$el.addClass('o_field_x2many o_field_x2many_' + viewType);
                        return self.renderer ? self.renderer.appendTo(self.$el) : self._super();
                    });
                }
            }
        },
    });

})