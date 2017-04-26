=======================================
 Generating unique static URLs in Odoo
=======================================

Since Sep 19th, 2015 we introduced a patch in Odoo to avoid bundling
of static assets when using a SPDY or HTTP/2 proxy like Nginx.
However caches may keep assets for seven days.

Changes:

- Generate URLs that change when the assets do.
- Increase the cache expiration time to 365 days.


TODO:

- Treat ``<img>`` the same.
