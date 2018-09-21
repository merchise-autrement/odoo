# -*- coding: utf-8 -*-
import base64
import os
import re
import hashlib
import itertools
import json
import textwrap
import uuid
from datetime import datetime
from subprocess import Popen, PIPE
from collections import OrderedDict
from odoo import fields, tools, SUPERUSER_ID
from odoo.tools.pycompat import string_types, to_text
from odoo.http import request
from odoo.modules.module import get_resource_path
from odoo.addons.base.ir.ir_qweb.qweb import escape
import psycopg2
from odoo.tools import func, misc

from rjsmin import jsmin as rjsmin


import logging
_logger = logging.getLogger(__name__)

MAX_CSS_RULES = 4095


class AssetError(Exception):
    pass


class AssetNotFound(AssetError):
    pass


class AssetsBundle(object):
    rx_css_import = re.compile("(@import[^;{]+;?)", re.M)
    rx_preprocess_imports = re.compile("""(@import\s?['"]([^'"]+)['"](;?))""")
    rx_css_split = re.compile("\/\*\! ([a-f0-9-]+) \*\/")

    # remains attribute is depreciated and will remove after v11
    def __init__(self, name, files, remains=None, env=None):
        self.name = name
        self.env = request.env if env is None else env
        self.max_css_rules = self.env.context.get('max_css_rules', MAX_CSS_RULES)
        self.javascripts = []
        self.stylesheets = []
        self.css_errors = []
        self._checksum = None
        self.files = files
        for f in files:
            if f['atype'] == 'text/sass':
                self.stylesheets.append(SassStylesheetAsset(self, url=f['url'], filename=f['filename'], inline=f['content'], media=f['media']))
            elif f['atype'] == 'text/less':
                self.stylesheets.append(LessStylesheetAsset(self, url=f['url'], filename=f['filename'], inline=f['content'], media=f['media']))
            elif f['atype'] == 'text/css':
                self.stylesheets.append(StylesheetAsset(self, url=f['url'], filename=f['filename'], inline=f['content'], media=f['media']))
            elif f['atype'] == 'text/javascript':
                self.javascripts.append(JavascriptAsset(self, url=f['url'], filename=f['filename'], inline=f['content']))

    # depreciated and will remove after v11
    def to_html(self, sep=None, css=True, js=True, debug=False, async_load=False, url_for=(lambda url: url),
                spdy=False, **kw):
        if 'async' in kw:
            _logger.warning("Using deprecated argument 'async' in to_html call, use 'async_load' instead.")
            async_load = kw['async']
        nodes = self.to_node(css=css, js=js, debug=debug, async_load=async_load, spdy=spdy)

        if sep is None:
            sep = u'\n            '
        response = []
        for tagName, attributes, content in nodes:
            html = u"<%s " % tagName
            for name, value in attributes.items():
                if value or isinstance(value, string_types):
                    html += u' %s="%s"' % (name, escape(to_text(value)))
            if content is None:
                html += u'/>'
            else:
                html += u'>%s</%s>' % (escape(to_text(content)), tagName)
            response.append(html)

        return sep + sep.join(response)

    def to_node(self, css=True, js=True, debug=False, async_load=False, spdy=False, **kw):
        """
        :returns [(tagName, attributes, content)] if the tag is auto close
        """
        if 'async' in kw:
            _logger.warning("Using deprecated argument 'async' in to_node call, use 'async_load' instead.")
            async_load = kw['async']
        response = []
        if debug == 'assets' or spdy:
            if css and self.stylesheets:
                is_css_preprocessed, old_attachments = self.is_css_preprocessed()
                if not is_css_preprocessed:
                    self.preprocess_css(
                        debug=debug,
                        old_attachments=old_attachments,
                        spdy=spdy
                    )
                    if self.css_errors:
                        msg = '\n'.join(self.css_errors)
                        response.append(JavascriptAsset(self, inline=self.dialog_message(msg)).to_node(spdy=spdy))
                        response.append(StylesheetAsset(self, url="/web/static/lib/bootstrap/css/bootstrap.css").to_node(spdy=spdy))
                if not self.css_errors:
                    for style in self.stylesheets:
                        response.append(style.to_node(spdy=spdy))

            if js:
                for jscript in self.javascripts:
                    response.append(jscript.to_node(spdy=spdy))
        else:
            if css and self.stylesheets:
                css_attachments = self.css() or []
                for attachment in css_attachments:
                    attr = OrderedDict([
                        ["type", "text/css"],
                        ["rel", "stylesheet"],
                        ["href", attachment.url],
                    ])
                    response.append(("link", attr, None))
                if self.css_errors:
                    msg = '\n'.join(self.css_errors)
                    response.append(JavascriptAsset(self, inline=self.dialog_message(msg)).to_node(spdy=spdy))
            if js and self.javascripts:
                attr = OrderedDict([
                    ["async", "async" if async_load else None],
                    ["type", "text/javascript"],
                    ["src", self.js().url],
                ])
                response.append(("script", attr, None))

        return response

    @func.lazy_property
    def last_modified(self):
        """Returns last modified date of linked files"""
        return max(itertools.chain(
            (asset.last_modified for asset in self.javascripts),
            (asset.last_modified for asset in self.stylesheets),
        ))

    @func.lazy_property
    def version(self):
        return self.checksum[0:7]

    @func.lazy_property
    def checksum(self):
        """
        Not really a full checksum.
        We compute a SHA1 on the rendered bundle + max linked files last_modified date
        """
        check = u"%s%s" % (json.dumps(self.files, sort_keys=True), self.last_modified)
        return hashlib.sha1(check.encode('utf-8')).hexdigest()

    def clean_attachments(self, type):
        """ Takes care of deleting any outdated ir.attachment records associated to a bundle before
        saving a fresh one.

        When `type` is css we need to check that we are deleting a different version (and not *any*
        version) because css may be paginated and, therefore, may produce multiple attachments for
        the same bundle's version.

        When `type` is js we need to check that we are deleting a different version (and not *any*
        version) because, as one of the creates in `save_attachment` can trigger a rollback, the
        call to `clean_attachments ` is made at the end of the method in order to avoid the rollback
        of an ir.attachment unlink (because we cannot rollback a removal on the filestore), thus we
        must exclude the current bundle.
        """
        ira = self.env['ir.attachment']
        domain = [
            ('url', '=like', '/web/content/%-%/{0}%.{1}'.format(self.name, type)),  # The wilcards are id, version and pagination number (if any)
            '!', ('url', '=like', '/web/content/%-{}/%'.format(self.version))
        ]

        # force bundle invalidation on other workers
        self.env['ir.qweb'].clear_caches()

        return ira.sudo().search(domain).unlink()

    def get_attachments(self, type, ignore_version=False):
        """ Return the ir.attachment records for a given bundle. This method takes care of mitigating
        an issue happening when parallel transactions generate the same bundle: while the file is not
        duplicated on the filestore (as it is stored according to its hash), there are multiple
        ir.attachment records referencing the same version of a bundle. As we don't want to source
        multiple time the same bundle in our `to_html` function, we group our ir.attachment records
        by file name and only return the one with the max id for each group.
        """
        version = "%" if ignore_version else self.version
        url_pattern = '/web/content/%-{0}/{1}{2}.{3}'.format(version, self.name, '.%' if type == 'css' else '', type)
        self.env.cr.execute("""
             SELECT max(id)
               FROM ir_attachment
              WHERE create_uid = %s
                AND url like %s
           GROUP BY datas_fname
           ORDER BY datas_fname
         """, [SUPERUSER_ID, url_pattern])
        attachment_ids = [r[0] for r in self.env.cr.fetchall()]
        return self.env['ir.attachment'].sudo().browse(attachment_ids)

    def save_attachment(self, type, content, inc=None):
        assert type in ('js', 'css')
        ira = self.env['ir.attachment']

        fname = '%s%s.%s' % (self.name, ('' if inc is None else '.%s' % inc), type)
        mimetype = 'application/javascript' if type == 'js' else 'text/css'
        values = {
            'name': "/web/content/%s" % type,
            'datas_fname': fname,
            'mimetype' : mimetype,
            'res_model': 'ir.ui.view',
            'res_id': False,
            'type': 'binary',
            'public': True,
            'datas': base64.b64encode(content.encode('utf8')),
        }
        attachment = ira.sudo().create(values)

        url = '/web/content/%s-%s/%s' % (attachment.id, self.version, fname)
        values = {
            'name': url,
            'url': url,
        }
        attachment.write(values)

        if self.env.context.get('commit_assetsbundle') is True:
            self.env.cr.commit()

        self.clean_attachments(type)

        return attachment

    def js(self):
        attachments = self.get_attachments('js')
        if not attachments:
            content = ';\n'.join(asset.minify() for asset in self.javascripts)
            return self.save_attachment('js', content)
        return attachments[0]

    def css(self):
        attachments = self.get_attachments('css')
        if not attachments:
            # get css content
            css = self.preprocess_css()
            if self.css_errors:
                return self.get_attachments('css', ignore_version=True)

            # move up all @import rules to the top
            matches = []
            css = re.sub(self.rx_css_import, lambda matchobj: matches.append(matchobj.group(0)) and '', css)
            matches.append(css)
            css = u'\n'.join(matches)

            # split for browser max file size and browser max expression
            re_rules = '([^{]+\{(?:[^{}]|\{[^{}]*\})*\})'
            re_selectors = '()(?:\s*@media\s*[^{]*\{)?(?:\s*(?:[^,{]*(?:,|\{(?:[^}]*\}))))'
            page = []
            pages = [page]
            page_selectors = 0
            for rule in re.findall(re_rules, css):
                selectors = len(re.findall(re_selectors, rule))
                if page_selectors + selectors <= self.max_css_rules:
                    page_selectors += selectors
                    page.append(rule)
                else:
                    pages.append([rule])
                    page = pages[-1]
                    page_selectors = selectors
            for idx, page in enumerate(pages):
                self.save_attachment("css", ' '.join(page), inc=idx)
            attachments = self.get_attachments('css')
        return attachments

    def dialog_message(self, message):
        return """
            (function (message) {
                if (window.__assetsBundleErrorSeen) return;
                window.__assetsBundleErrorSeen = true;

                document.addEventListener("DOMContentLoaded", function () {
                    var alertTimeout = setTimeout(alert.bind(window, message), 0);
                    if (typeof odoo === "undefined") return;

                    odoo.define("AssetsBundle.ErrorMessage", function (require) {
                        "use strict";

                        var base = require("web_editor.base");
                        var core = require("web.core");
                        var Dialog = require("web.Dialog");

                        var _t = core._t;

                        clearTimeout(alertTimeout);

                        base.ready().then(function () {
                            new Dialog(null, {
                                title: _t("Style error"),
                                $content: $("<div/>")
                                    .append($("<p/>", {text: _t("The style compilation failed, see the error below. Your recent actions may be the cause, please try reverting the changes you made.")}))
                                    .append($("<pre/>", {html: message})),
                            }).open();
                        });
                    });
                });
            })("%s");
        """ % message.replace('"', '\\"').replace('\n', '&NewLine;')

    def is_css_preprocessed(self):
        preprocessed = True
        attachments = None
        for atype in (SassStylesheetAsset, LessStylesheetAsset):
            outdated = False
            assets = dict((asset.html_url, asset) for asset in self.stylesheets if isinstance(asset, atype))
            if assets:
                assets_domain = [('url', 'in', list(assets.keys()))]
                attachments = self.env['ir.attachment'].sudo().search(assets_domain)
                for attachment in attachments:
                    asset = assets[attachment.url]
                    if asset.last_modified > fields.Datetime.from_string(attachment['__last_update']):
                        outdated = True
                        break
                    if asset._content is None:
                        asset._content = attachment.datas and base64.b64decode(attachment.datas).decode('utf8') or ''
                        if not asset._content and attachment.file_size > 0:
                            asset._content = None # file missing, force recompile

                if any(asset._content is None for asset in assets.values()):
                    outdated = True

                if outdated:
                    preprocessed = False

        return preprocessed, attachments

    def preprocess_css(self, debug=False, old_attachments=None, spdy=False):
        """
            Checks if the bundle contains any sass/less content, then compiles it to css.
            Returns the bundle's flat css.
        """
        from odoo.http import STATIC_CACHE
        for atype in (SassStylesheetAsset, LessStylesheetAsset):
            assets = [asset for asset in self.stylesheets if isinstance(asset, atype)]
            if assets:
                cmd = assets[0].get_command()
                source = '\n'.join([asset.get_source() for asset in assets])
                compiled = self.compile_css(cmd, source)
                if not self.css_errors and old_attachments:
                    old_attachments.unlink()
                    old_attachments = None

                fragments = self.rx_css_split.split(compiled)
                at_rules = fragments.pop(0)
                if at_rules:
                    # Sass and less moves @at-rules to the top in order to stay css 2.1 compatible
                    self.stylesheets.insert(0, StylesheetAsset(self, inline=at_rules))
                while fragments:
                    asset_id = fragments.pop(0)
                    asset = next(asset for asset in self.stylesheets if asset.id == asset_id)
                    asset._content = fragments.pop(0)

                    if debug or spdy:
                        if debug:
                            asset_content = asset.content
                        else:
                            asset_content = asset.minify()
                        try:
                            fname = os.path.basename(asset.url)
                            url = asset.html_url
                            with self.env.cr.savepoint():
                                self.env['ir.attachment'].sudo().create(dict(
                                    datas=base64.b64encode(asset_content.encode('utf8')),
                                    mimetype='text/css',
                                    type='binary',
                                    name=url,
                                    url=url,
                                    datas_fname=fname,
                                    res_model=False,
                                    res_id=False,
                                    cache_control_header='max-age=%d, public' % STATIC_CACHE
                                ))

                            if self.env.context.get('commit_assetsbundle') is True:
                                self.env.cr.commit()
                        except psycopg2.Error:
                            pass

        return '\n'.join(asset.minify() for asset in self.stylesheets)

    def compile_css(self, cmd, source):
        """Sanitizes @import rules, remove duplicates @import rules, then compile"""
        imports = []

        def sanitize(matchobj):
            ref = matchobj.group(2)
            line = '@import "%s"%s' % (ref, matchobj.group(3))
            if '.' not in ref and line not in imports and not ref.startswith(('.', '/', '~')):
                imports.append(line)
                return line
            msg = "Local import '%s' is forbidden for security reasons." % ref
            _logger.warning(msg)
            self.css_errors.append(msg)
            return ''
        source = re.sub(self.rx_preprocess_imports, sanitize, source)

        try:
            compiler = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        except Exception:
            msg = "Could not execute command %r" % cmd[0]
            _logger.error(msg)
            self.css_errors.append(msg)
            return ''
        result = compiler.communicate(input=source.encode('utf-8'))
        if compiler.returncode:
            cmd_output = ''.join(misc.ustr(result))
            if not cmd_output:
                cmd_output = "Process exited with return code %d\n" % compiler.returncode
            error = self.get_preprocessor_error(cmd_output, source=source)
            _logger.warning(error)
            self.css_errors.append(error)
            return ''
        compiled = result[0].strip().decode('utf8')
        return compiled

    def get_preprocessor_error(self, stderr, source=None):
        """Improve and remove sensitive information from sass/less compilator error messages"""
        error = misc.ustr(stderr).split('Load paths')[0].replace('  Use --trace for backtrace.', '')
        if 'Cannot load compass' in error:
            error += "Maybe you should install the compass gem using this extra argument:\n\n" \
                     "    $ sudo gem install compass --pre\n"
        error += "This error occured while compiling the bundle '%s' containing:" % self.name
        for asset in self.stylesheets:
            if isinstance(asset, PreprocessedCSS):
                error += '\n    - %s' % (asset.url if asset.url else '<inline sass>')
        return error


class WebAsset(object):
    html_url_format = '%s'
    _content = None
    _filename = None
    _ir_attach = None
    _id = None

    def __init__(self, bundle, inline=None, url=None, filename=None):
        self.bundle = bundle
        self.inline = inline
        self._filename = filename
        self.url = url
        self.html_url_args = url
        if not inline and not url:
            raise Exception("An asset should either be inlined or url linked, defined in bundle '%s'" % bundle.name)

    @func.lazy_property
    def id(self):
        if self._id is None: self._id = str(uuid.uuid4())
        return self._id

    @func.lazy_property
    def name(self):
        name = '<inline asset>' if self.inline else self.url
        return "%s defined in bundle '%s'" % (name, self.bundle.name)

    @property
    def html_url(self):
        return self.html_url_format % self.html_url_args

    def stat(self):
        if not (self.inline or self._filename or self._ir_attach):
            path = (segment for segment in self.url.split('/') if segment)
            self._filename = get_resource_path(*path)
            if self._filename:
                return
            try:
                # Test url against ir.attachments
                fields = ['__last_update', 'datas', 'mimetype']
                domain = [('type', '=', 'binary'), ('url', '=', self.url)]
                attach = self.bundle.env['ir.attachment'].sudo().search_read(domain, fields)
                self._ir_attach = attach[0]
            except Exception:
                raise AssetNotFound("Could not find %s" % self.name)

    # depreciated and will remove after v11
    def to_html(self, spdy=False):
        tagName, attributes, content = self.to_node(spdy=spdy)
        html = u"<%s " % tagName
        for name, value in attributes.items():
            if value or isinstance(value, string_types):
                html += u' %s="%s"' % (name, escape(to_text(value)))
        if content is None:
            html += u'/>'
        else:
            html += u'>%s</%s>' % (escape(to_text(content)), tagName)
        return html

    def to_node(self, spdy=False):
        raise NotImplementedError()

    @func.lazy_property
    def last_modified(self):
        try:
            self.stat()
            if self._filename:
                return datetime.fromtimestamp(os.path.getmtime(self._filename))
            elif self._ir_attach:
                server_format = tools.DEFAULT_SERVER_DATETIME_FORMAT
                last_update = self._ir_attach['__last_update']
                try:
                    return datetime.strptime(last_update, server_format + '.%f')
                except ValueError:
                    return datetime.strptime(last_update, server_format)
        except Exception:
            pass
        return datetime(1970, 1, 1)

    @property
    def content(self):
        if self._content is None:
            self._content = self.inline or self._fetch_content()
        return self._content

    def _fetch_content(self):
        """ Fetch content from file or database"""
        try:
            self.stat()
            if self._filename:
                with open(self._filename, 'rb') as fp:
                    return fp.read().decode('utf-8')
            else:
                return base64.b64decode(self._ir_attach['datas']).decode('utf-8')
        except UnicodeDecodeError:
            raise AssetError('%s is not utf-8 encoded.' % self.name)
        except IOError:
            raise AssetNotFound('File %s does not exist.' % self.name)
        except:
            raise AssetError('Could not get content for %s.' % self.name)

    def minify(self):
        return self.content

    def with_header(self, content=None):
        if content is None:
            content = self.content
        return '\n/* %s */\n%s' % (self.name, content)

    @property
    def versionhash(self):
        self.stat()
        if self._filename:
            try:
                return os.path.getmtime(self._filename)
            except:
                _logger.exception(
                    "Error while hashing asset '%s'",
                    self._filename
                )
                return None
        else:
            return None


class JavascriptAsset(WebAsset):
    def minify(self):
        return self.with_header(rjsmin(self.content))

    def _fetch_content(self):
        try:
            return super(JavascriptAsset, self)._fetch_content()
        except AssetError as e:
            return u"console.error(%s);" % json.dumps(to_text(e))

    def to_node(self, spdy=False):
        if self.url:
            return ("script", OrderedDict([
                ["type", "text/javascript"],
                ["src", self.html_url],
            ]), None)
        else:
            return ("script", OrderedDict([
                ["type", "text/javascript"],
                ["charset", "utf-8"],
            ]), self.with_header())


class StylesheetAsset(WebAsset):
    rx_import = re.compile(r"""@import\s+('|")(?!'|"|/|https?://)""", re.U)
    rx_url = re.compile(r"""url\s*\(\s*('|"|)(?!'|"|/|https?://|data:)""", re.U)
    rx_sourceMap = re.compile(r'(/\*# sourceMappingURL=.*)', re.U)
    rx_charset = re.compile(r'(@charset "[^"]+";)', re.U)

    def __init__(self, *args, **kw):
        self.media = kw.pop('media', None)
        super(StylesheetAsset, self).__init__(*args, **kw)

    @property
    def content(self):
        content = super(StylesheetAsset, self).content
        if self.media:
            content = '@media %s { %s }' % (self.media, content)
        return content

    def _fetch_content(self):
        try:
            content = super(StylesheetAsset, self)._fetch_content()
            web_dir = os.path.dirname(self.url)

            if self.rx_import:
                content = self.rx_import.sub(
                    r"""@import \1%s/""" % (web_dir,),
                    content,
                )

            if self.rx_url:
                content = self.rx_url.sub(
                    r"url(\1%s/" % (web_dir,),
                    content,
                )

            if self.rx_charset:
                # remove charset declarations, we only support utf-8
                content = self.rx_charset.sub('', content)

            return content
        except AssetError as e:
            self.bundle.css_errors.append(str(e))
            return ''

    def minify(self):
        # remove existing sourcemaps, make no sense after re-mini
        content = self.rx_sourceMap.sub('', self.content)
        # comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.S)
        # space
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r' *([{}]) *', r'\1', content)
        return self.with_header(content)

    def to_node(self, spdy=False):
        if self.url:
            attr = OrderedDict([
                ["type", "text/css"],
                ["rel", "stylesheet"],
                ["href", self.html_url],
                ["media", escape(to_text(self.media)) if self.media else None]
            ])
            return ("link", attr, None)
        else:
            attr = OrderedDict([
                ["type", "text/css"],
                ["media", escape(to_text(self.media)) if self.media else None]
            ])
            return ("style", attr, self.with_header())


class PreprocessedCSS(StylesheetAsset):
    rx_import = None

    def __init__(self, *args, **kw):
        super(PreprocessedCSS, self).__init__(*args, **kw)
        self.html_url_format = '%%s/%s/%%s.css' % self.bundle.name
        self.html_url_args = tuple(self.url.rsplit('/', 1))

    def get_source(self):
        content = self.inline or self._fetch_content()
        return "/*! %s */\n%s" % (self.id, content)

    def get_command(self):
        raise NotImplementedError


class SassStylesheetAsset(PreprocessedCSS):
    rx_indent = re.compile(r'^( +|\t+)', re.M)
    indent = None
    reindent = '    '

    def minify(self):
        return self.with_header()

    def get_source(self):
        content = textwrap.dedent(self.inline or self._fetch_content())

        def fix_indent(m):
            # Indentation normalization
            ind = m.group()
            if self.indent is None:
                self.indent = ind
                if self.indent == self.reindent:
                    # Don't reindent the file if identation is the final one (reindent)
                    raise StopIteration()
            return ind.replace(self.indent, self.reindent)

        try:
            content = self.rx_indent.sub(fix_indent, content)
        except StopIteration:
            pass
        return "/*! %s */\n%s" % (self.id, content)

    def get_command(self):
        try:
            sass = misc.find_in_path('sass')
        except IOError:
            sass = 'sass'
        return [sass, '--stdin', '-t', 'compressed', '--unix-newlines', '--compass',
                '-r', 'bootstrap-sass']


class LessStylesheetAsset(PreprocessedCSS):
    def get_command(self):
        try:
            if os.name == 'nt':
                lessc = misc.find_in_path('lessc.cmd')
            else:
                lessc = misc.find_in_path('lessc')
        except IOError:
            lessc = 'lessc'
        lesspath = get_resource_path('web', 'static', 'lib', 'bootstrap', 'less')
        return [lessc, '-', '--no-js', '--no-color', '--include-path=%s' % lesspath]
