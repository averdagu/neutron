#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

import fixtures
import netaddr
from neutron_lib import exceptions
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import uuidutils

from neutron.agent.linux import ip_lib
from neutron.agent.linux import utils as n_utils
from neutron.tests.common import config_fixtures

LOG = logging.getLogger(__name__)


class LogFileExtenderMeta(type):
    def __new__(cls, name, bases, dct):
        klass = type.__new__(cls, name, bases, dct)

        for parent in bases:
            try:
                if klass.LOGS_TO_COLLECT is not parent.LOGS_TO_COLLECT:
                    klass.LOGS_TO_COLLECT.extend(parent.LOGS_TO_COLLECT)
            except AttributeError:
                pass

        return klass


class ConfigFixture(config_fixtures.ConfigFileFixture):
    pass


class Container(fixtures.Fixture):
    def __init__(self, host, image, networks, debug=False):
        self.host = host
        self.image = image
        self.name = "{:s}-{:s}".format(image, uuidutils.generate_uuid())
        self.networks = networks or []
        self.debug = debug

    def _setUp(self):
        self.start()

    def start(self):
        cmd = ['podman', 'run', '-d', '--name', self.name, '--mount',
               'type=bind,src=%s,target=/mnt/host' % self.host.host_dir,
               '--privileged=true']

        if self.debug:
            cmd.insert(1, '--log-level=debug')

        if self.networks:
            cmd.extend(['--network', ','.join([
                net.uuid for net in self.networks])])

        cmd.extend(['localhost/{:s}'.format(self.image)])

        try:
            n_utils.execute(
                cmd,
                run_as_root=True)
        except exceptions.ProcessExecutionError as pe:
            LOG.debug("Failed to start container %(name)s: %(exc)s",
                {'name': self.name,
                 'exc': pe})
            n_utils.execute(
                ['podman', 'rm', '-f', self.name],
                run_as_root=True, check_exit_code=False)
            raise

    def execute(self, cmd):
        cmd = ['podman', 'exec', self.name] + cmd
        return n_utils.execute(
            cmd,
            run_as_root=True)

    @property
    def inspect(self):
        if not hasattr(self, '_inspect'):
            cmd = ['podman', 'inspect', self.name]
            self._inspect = jsonutils.loads(
                n_utils.execute(
                    cmd,
                    run_as_root=True))[0]
        return self._inspect

    @property
    def network_settings(self):
        return self.inspect["NetworkSettings"]

    @property
    def hostname(self):
        return self.inspect["Config"]["Hostname"]

    @property
    def ip_wrapper(self):
        if not hasattr(self, '_ip_wrapper'):
            net_ns = self.network_settings["SandboxKey"].split('/')[-1]
            self._ip_wrapper = ip_lib.IPWrapper(net_ns)

        return self._ip_wrapper

    def __str__(self):
        return self.name

    __repr__ = __str__


class Host(fixtures.Fixture, metaclass=LogFileExtenderMeta):
    IMAGE_NAME = None
    BR_INT = 'br-int'
    LOGS_TO_COLLECT = [
        '/var/log/openvswitch/ovs-vswitchd.log',
        '/var/log/openvswitch/ovsdb-server.log',
        '/var/log/ovn/ovn-controller.log',
    ]

    def __init__(self, networks, test_log_dir):
        self.container = Container(self, self.IMAGE_NAME, networks)
        self.test_log_dir = test_log_dir

    def _setUp(self):
        self.uuid = uuidutils.generate_uuid()
        self.working_dir = self.useFixture(fixtures.TempDir()).path
        LOG.debug("Creating working host directory for container %s",
                  self.container)
        os.mkdir(self.host_dir)
        self.pre_configure()
        self.start()
        self.addCleanup(self.collect_logs)
        self.post_configure()

    def start(self):
        self.useFixture(self.container)

    @property
    def host_dir(self):
        return os.path.join(self.working_dir, 'host')

    @property
    def hostname(self):
        return self.container.hostname

    def pre_configure(self):
        raise NotImplementedError

    def post_configure(self):
        raise NotImplementedError

    @property
    def control_ip(self):
        return self._get_device_ip(device_index=0)

    @property
    def tunnel_ip(self):
        return self._get_device_ip(device_index=1)

    def _get_device_ip(self, device_index):
        network = netaddr.IPNetwork(
            self.container.ip_wrapper.get_devices()[
                device_index].addr.list()[0]['cidr'])
        return str(network.ip)

    def collect_logs(self):
        destination = os.path.join(self.test_log_dir, self.container.name)
        LOG.debug("Collecting logs from container %s to directory %s",
                  self.container.name, destination)
        os.mkdir(destination)
        for logpath in self.LOGS_TO_COLLECT:
            source = "%(container)s:%(file)s" % {
                'container': self.container.name,
                'file': logpath
            }
            n_utils.execute(['podman', 'cp', source, destination],
                            run_as_root=True, check_exit_code=False)


class NeutronServerOvn(Host):
    IMAGE_NAME = 'neutron-server-ovn'
    LOGS_TO_COLLECT = [
        '/var/log/ovn/ovsdb-server-nb.log',
        '/var/log/ovn/ovsdb-server-sb.log',
        '/var/log/ovn/ovn-northd.log',
        '/mnt/host/server.log',
        '/mnt/host/neutron.conf',
    ]

    def __init__(self, database_url, networks, test_log_dir):
        super(NeutronServerOvn, self).__init__(networks, test_log_dir)
        self.database_url = str(database_url)

    def pre_configure(self):
        config_dict = {
            'DEFAULT': {
                'host': self.container.name,
                'api_paste_config': '/usr/local/etc/neutron/api-paste.ini',
                'core_plugin': 'ml2',
                'service_plugins': 'ovn-router,trunk,port_forwarding',
                'auth_strategy': 'noauth',
                'debug': 'True',
                'api_workers': '4',
                'rpc_workers': '0',
                # TODO(jlibosva): Configure rabbit connection when DHCP agent
                #                 is present.
                'transport_url': 'fake:/',
            },
            'database': {
                'connection': self.database_url,
            },
            'ml2': {
                'mechanism_drivers': 'ovn,logger',
                'type_drivers': 'local,flat,vlan,geneve',
                'tenant_network_types': 'geneve',
                'extension_drivers': 'port_security,dns',
            },
            'oslo_concurrency': {
                'lock_path': '$state_path/lock',
            },
            'ml2_type_geneve': {
                'max_header_size': '38',
                'vni_ranges': '1:65536',
            },
            'ovn': {
                'ovn_nb_connection': 'tcp:127.0.0.1:6641',
                'ovn_sb_connection': 'tcp:127.0.0.1:6642',
                'neutron_sync_mode': 'log',
                'ovn_l3_scheduler': 'leastloaded',
            },
            'securitygroup': {
                'enable_security_group': 'true',
            },
        }
        self.useFixture(
            ConfigFixture('neutron.conf', config_dict, self.host_dir))

    def post_configure(self):
        cmd = [
            'ovs-vsctl', 'set', 'open', '.',
            'external-ids:ovn-bridge=%s' % self.BR_INT,
            '--', 'set', 'open', '.',
            'external-ids:ovn-remote=unix:'
            '/usr/var/run/openvswitch/ovnsb_db.sock',
            '--', 'set', 'open', '.',
            'external-ids:ovn-encap-ip=%(local_ip)s' % {
                'local_ip': self.tunnel_ip},
            '--', 'set', 'open', '.', 'external-ids:ovn-encap-type=geneve']
        self.container.execute(cmd)


class NeutronCompute(Host):
    IMAGE_NAME = 'neutron-ovn-controller'

    def __init__(self, networks, controller_ip, test_log_dir):
        super(NeutronCompute, self).__init__(networks, test_log_dir)
        self.controller_ip = controller_ip

    def pre_configure(self):
        pass

    def post_configure(self):
        def get_cmd(port):
            return [
                'ovs-vsctl', 'set', 'open', '.',
                'external-ids:ovn-bridge=%s' % self.BR_INT,
                '--', 'set', 'open', '.',
                'external-ids:ovn-remote=''tcp:%(controller_ip)s:%(port)d' % {
                    'controller_ip': self.controller_ip,
                    'port': port
                }, '--', 'set', 'open', '.',
                'external-ids:ovn-encap-ip=%(local_ip)s' % {
                    'local_ip': self.tunnel_ip},
                '--', 'set', 'open', '.', 'external-ids:ovn-encap-type=geneve',
            ]
        for port in (6642, 6648, 6642):
            cmd = get_cmd(port)
            self.container.execute(cmd)

    def vif_plug(self, namespace, port):
        iface_name = 'tap-%s' % port['id'][:11]
        # NOTE(jlibosva): ovs-vsctl considers colons to be a separator. When
        #                 putting a mac address, we need to escape all colons
        mac_address = port['mac_address'].replace(':', '\\:')
        self.container.execute(
            ['ovs-vsctl', 'add-port', 'br-int', iface_name, '--',
             'set', 'Interface', iface_name, 'type=internal', '--',
             'set', 'Interface', iface_name,
             'external_ids:iface-id=%s' % port['id'], '--',
             'set', 'Interface', iface_name, 'mac=%s' % mac_address])
        self.container.execute(
            ['ip', 'l', 's', iface_name, 'netns', namespace])
