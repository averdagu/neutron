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

from concurrent import futures
from datetime import datetime
import os

from neutronclient.common import exceptions as nc_exc
from neutronclient.v2_0 import client as n_client
from oslo_config import cfg
from oslo_log import log as logging

from neutron.agent.linux import utils as n_utils
from neutron.common import utils as n_common_utils
from neutron.tests import base
from neutron.tests.fullstack.resources import client
from neutron.tests.george.resources import environment
from neutron.tests.george.resources import network
from neutron.tests.unit import testlib_api

LOG_DIR = os.path.join(
    os.environ.get('OS_LOG_PATH', '/tmp'), 'george-logs')
LOG = logging.getLogger(__name__)


def setup_privsep():
    privsep_executable_path = os.path.join(
        os.getenv('OS_VENV'), 'bin', 'privsep-helper')
    cfg.CONF.set_override(
        'helper_command',
        'sudo -E %s' % privsep_executable_path, 'privsep')


class EnvironmentException(Exception):
    pass


class BaseGeorgeTestCase(testlib_api.MySQLTestCaseMixin,
                         testlib_api.SqlTestCase):
    BUILD_WITH_MIGRATIONS = True
    COMPUTES_NUM = None

    def __init__(self, *args, **kwargs):
        super(BaseGeorgeTestCase, self).__init__(*args, **kwargs)
        self.server = None
        self.computes = []

    def setUp(self):
        super(BaseGeorgeTestCase, self).setUp()
        if not self.COMPUTES_NUM:
            raise RuntimeError("COMPUTES_NUM is not set")

        self.setup_logging()
        setup_privsep()
        self._create_environment()

    def _delete_nodes(self):
        container_names = [
            node.container.name for node in self.computes]
        LOG.debug("Stopping compute containers %s", container_names)
        if container_names:
            n_utils.execute(['podman', 'stop', '-t', '1'] + container_names,
                            run_as_root=True, check_exit_code=False)
        if self.server:
            LOG.debug("Stopping server container %s",
                      self.server.container.name)
            n_utils.execute(['podman', 'stop', '-t', '30',
                            self.server.container.name],
                            run_as_root=True,
                            check_exit_code=False)
            container_names.append(self.server.container.name)
        LOG.debug("Removing containers %s", container_names)
        if container_names:
            n_utils.execute(['podman', 'rm', '-f'] + container_names,
                            run_as_root=True, check_exit_code=False)

    def _create_nodes(self, networks, database_url):
        self.addCleanup(self._delete_nodes)
        self.server = environment.NeutronServerOvn(
            database_url, networks, self.test_log_dir)
        self.useFixture(self.server)

        self.computes = [
            environment.NeutronCompute(
                networks, self.server.control_ip, self.test_log_dir)
            for i in range(self.COMPUTES_NUM)]

        with futures.ThreadPoolExecutor(
                max_workers=self.COMPUTES_NUM) as executor:
            for compute in self.computes:
                executor.submit(self.useFixture, compute)

    def _create_environment(self):
        control_net = self.useFixture(
            network.Network('ctlplane', gateway=True))
        tunnel_net = self.useFixture(network.Network('tunnelnet'))
        networks = [control_net, tunnel_net]

        database_url = str(
            self.engine.url).replace('localhost', control_net.gateway_ip)

        self._create_nodes(networks, database_url)

        url = "http://%s:9696" % self.server.control_ip
        self.safe_client = self.useFixture(
            client.ClientFixture(
                n_client.Client(auth_strategy="noauth", endpoint_url=url,
                                timeout=30)))

        self.wait_until_env_is_up()

    def wait_until_env_is_up(self):
        import ipdb; ipdb.set_trace()
        n_common_utils.wait_until_true(
            self._env_is_ready,
            timeout=60,
            sleep=5,
            exception=EnvironmentException(
                "The environment didn't come up."))

    def _env_is_ready(self):
        try:
            running_agents = len(
                self.safe_client.client.list_agents()['agents'])
            agents_count = len(self.computes)
            return running_agents == agents_count
        except nc_exc.NeutronClientException:
            return False

    def setup_logging(self):
        dirname = "%(timestamp)s-%(id)s" % {
            'timestamp': datetime.now().strftime("%y-%m-%d_%H-%M-%S"),
            'id': self.id()
        }
        self.test_log_dir = os.path.join(LOG_DIR, dirname)
        base.setup_test_logging(
            cfg.CONF, self.test_log_dir, "testrun.txt")
