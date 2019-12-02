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

import netaddr
from neutron_lib import exceptions as n_lib_e
from oslo_utils import uuidutils

from neutron.common import utils as n_common_utils
from neutron.tests.common import machine_fixtures
from neutron.tests.george.resources import fixtures


class FakeMachine(machine_fixtures.FakeMachineBase):
    def __init__(self, host, network_id, tenant_id, n_client):
        self.host = host
        self.network_id = network_id
        self.tenant_id = tenant_id
        self.n_client = n_client
        self.instance_id = uuidutils.generate_uuid()
        self.netns = None
        self.neutron_port = None

    def _setUp(self):
        super(FakeMachine, self)._setUp()
        self._create()

    def _create(self):
        self.netns = self.useFixture(
            fixtures.ContainerNamespaceFixture(
                self.host.container,
                "vm-%s" % self.instance_id)
        )
        self.neutron_port = self.n_client.create_port(
            network_id=self.network_id,
            tenant_id=self.tenant_id,
            hostname=self.host.hostname)
        self.host.vif_plug(self.netns.name, self.neutron_port)

    def execute(self, cmd):
        return self.netns.execute(cmd)

    @property
    def ip_address(self):
        return self.neutron_port['fixed_ips'][0]['ip_address']

    def assert_ping(self, dst_ip, timeout=1, count=1):
        ipversion = netaddr.IPAddress(dst_ip).version
        ping_command = 'ping' if ipversion == 4 else 'ping6'
        self.execute([ping_command, '-c', count, '-W', timeout, dst_ip])

    def wait_until_boot(self):
        def is_ready():
            if not self.neutron_port:
                return False
            iface_name = 'tap-%s' % self.neutron_port['id'][:11]
            try:
                self.netns.execute(['ip', 'l', 'show', iface_name])
                return True
            except n_lib_e.ProcessExecutionError:
                return False
        n_common_utils.wait_until_true(
            is_ready,
            timeout=10,
            exception=Exception("VM didn't get created neutron port in time"))
        iface_name = 'tap-%s' % self.neutron_port['id'][:11]
        self.execute(['ip', 'l', 's', iface_name, 'up'])
        # TODO(jlibosva): Use DHCP client here instead of static configuration
        self.execute(['ip', 'a', 'a', '%s/24' % self.ip_address,
                      'dev', iface_name])
