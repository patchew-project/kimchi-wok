#
# Project Wok
#
# Copyright IBM Corp, 2015-2017
#
# Code derived from Project Kimchi
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA

import cherrypy
import json
import os
import time
from distutils.version import LooseVersion

from wok import auth
from wok import template
from wok.i18n import messages
from wok.config import paths as wok_paths
from wok.control import sub_nodes
from wok.control.base import Resource
from wok.control.utils import parse_request
from wok.exception import MissingParameter, UnauthorizedError
from wok.reqlogger import log_request


ROOT_REQUESTS = {
    'POST': {
        'login': "WOKROOT0001L",
        'logout': "WOKROOT0002L",
    },
}


class Root(Resource):
    def __init__(self, model, dev_env=False):
        super(Root, self).__init__(model)
        self._handled_error = ['error_page.400', 'error_page.404',
                               'error_page.405', 'error_page.406',
                               'error_page.415', 'error_page.500',
                               'error_page.403']

        if not dev_env:
            self._cp_config = dict([(key, self.error_production_handler)
                                    for key in self._handled_error])
        else:
            self._cp_config = dict([(key, self.error_development_handler)
                                    for key in self._handled_error])

    def _set_CSP(self):
        # set Content-Security-Policy to prevent XSS attacks
        headers = cherrypy.response.headers
        headers['Content-Security-Policy'] = "default-src 'self'"

    def error_production_handler(self, status, message, traceback, version):
        self._set_CSP()

        data = {'code': status, 'reason': message}
        res = template.render('error.html', data)

        if (type(res) is unicode and
                LooseVersion(cherrypy.__version__) < LooseVersion('3.2.5')):
            res = res.encode("utf-8")
        return res

    def error_development_handler(self, status, message, traceback, version):
        self._set_CSP()

        data = {'code': status, 'reason': message,
                'call_stack': cherrypy._cperror.format_exc()}
        res = template.render('error.html', data)

        if (type(res) is unicode and
                LooseVersion(cherrypy.__version__) < LooseVersion('3.2.5')):
            res = res.encode("utf-8")
        return res

    def get(self):
        last_page = cherrypy.request.cookie.get("lastPage")
        # when session timeout, only session cookie is None.
        # when first login, both session and lastPage are None.
        if (cherrypy.session.originalid is None and last_page is None and
           not template.can_accept('application/json') and
           template.can_accept_html()):
            raise cherrypy.HTTPRedirect("/login.html", 303)

        return self.default(self.default_page)

    @cherrypy.expose
    def default(self, page, **kwargs):
        if page.endswith('.html'):
            return template.render(page, kwargs)
        if page.endswith('.json'):
            cherrypy.response.headers['Content-Type'] = \
                'application/json;charset=utf-8'
            context = template.render_cheetah_file(page, None)
            return context.encode("utf-8")
        raise cherrypy.HTTPError(404)

    @cherrypy.expose
    def tabs(self, page, **kwargs):
        # In order to load the Guests tab, we also use Cheetah in the tab
        # template to save the delay of the extra get to the guest page
        # For that, the tab template needs to know the correct path to ui files
        paths = cherrypy.request.app.root.paths
        script_name = cherrypy.request.app.script_name
        last_page = script_name.lstrip("/") + "/tabs/" + page[:-5]

        data = {}
        data['ui_dir'] = paths.ui_dir

        data['scripts'] = []
        for plugin, app in cherrypy.tree.apps.iteritems():
                if app.root.extends is not None:
                    scripts = app.root.extends.get(script_name, {})
                    if page in scripts.keys():
                        data['scripts'].append(scripts[page])

        if page.endswith('.html'):
            context = template.render('/tabs/' + page, data)
            cherrypy.response.cookie["lastPage"] = "/#" + last_page
            cherrypy.response.cookie['lastPage']['path'] = '/'
            return context
        raise cherrypy.HTTPError(404)


class WokRoot(Root):
    def __init__(self, model, dev_env=False):
        super(WokRoot, self).__init__(model, dev_env)
        self.default_page = 'wok-ui.html'
        for ident, node in sub_nodes.items():
            setattr(self, ident, node(model))
        with open(os.path.join(wok_paths.src_dir, 'API.json')) as f:
            self.api_schema = json.load(f)
        self.paths = wok_paths
        self.domain = 'wok'
        self.messages = messages
        self.extends = None
        self.failed_logins = []
        self.fail_timeout = 30

        # set user log messages and make sure all parameters are present
        self.log_map = ROOT_REQUESTS
        self.log_args.update({'username': ''})

    @cherrypy.expose
    def login(self, *args):
        def _raise_timeout():
            details = e = UnauthorizedError("WOKAUTH0004E",
                                            {"seconds": self.fail_timeout})
            log_request(code, params, details, method, 403)
            raise cherrypy.HTTPError(403, e.message)

        details = None
        method = 'POST'
        code = self.getRequestMessage(method, 'login')

        try:
            params = parse_request()
            username = params['username']
            password = params['password']
        except KeyError, item:
            details = e = MissingParameter('WOKAUTH0003E', {'item': str(item)})
            log_request(code, params, details, method, 400)
            raise cherrypy.HTTPError(400, e.message)

        # check for repetly
        l = len(self.failed_logins)
        if l >= 3:

            # verify if timeout is still valid
            last_try = self.failed_logins[l - 1]
            if time.time() < (last_try["time"] + self.fail_timeout):
                _raise_timeout()
        try:
            status = 200
            user_info = auth.login(username, password)

            # user logged sucessfuly: reset counters
            self.failed_logins = []
            self.timeout = 30
        except cherrypy.HTTPError, e:
            # store time and prevent too much tries
            self.failed_logins.append({"user": username,
                                       "time": time.time()})

            # more than 3 fails: raise error
            if len(self.failed_logins) > 3:
                self.fail_timeout += (len(self.failed_logins) - 3) * 30
                _raise_timeout()

            status = e.status
            raise
        finally:
            log_request(code, params, details, method, status)

        return json.dumps(user_info)

    @cherrypy.expose
    def logout(self):
        method = 'POST'
        code = self.getRequestMessage(method, 'logout')
        params = {'username': cherrypy.session.get(auth.USER_NAME, 'N/A')}

        auth.logout()

        log_request(code, params, None, method, 200, user=params['username'])

        return '{}'
