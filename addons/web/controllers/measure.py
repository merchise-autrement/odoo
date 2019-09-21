#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------
# Copyright (c) Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can do what the LICENCE file allows you to.
#

"""Werkzeug controller to export RPC debug data in prometheus format

"""
from odoo import http
from werkzeug.wrappers import Response


class Metrics(http.Controller):
    @http.route("/.well-known/prometheus/metrics", type="http", auth="none")
    def get_server_rpc_data(self):
        def generate_response():
            yield """# HELP mercurio_rpc_request Metrics about Odoo RPC performance\n# TYPE mercurio_rpc_request gauge\n"""
            while http.request_log_entries:
                data = http.request_log_entries.pop()
                time = data.pop("time", 0)
                timestamp = data.pop("timestamp", 0)
                if data:
                    items = ",".join(f'{k!s}="{v}"' for k, v in data.items())
                    yield f"mercurio_rpc_request{{{items}}} {time} {timestamp}\n"

        return Response(generate_response())
