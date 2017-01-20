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


from wok.exception import NotFoundError
from wok.utils import get_plugins, load_plugin_conf, set_plugin_state


class PluginsModel(object):
    def __init__(self, **kargs):
        pass

    def get_list(self):
        return [plugin for (plugin, config) in get_plugins()]


class PluginModel(object):
    def __init__(self, **kargs):
        pass

    def lookup(self, name):
        name = name.encode('utf-8')

        plugin_conf = load_plugin_conf(name)
        if not plugin_conf:
            raise NotFoundError("WOKPLUGIN0001E", {'name': name})

        return {"name": name, "enabled": plugin_conf['wok']['enable']}

    def enable(self, name):
        set_plugin_state(name, True)

    def disable(self, name):
        set_plugin_state(name, False)
