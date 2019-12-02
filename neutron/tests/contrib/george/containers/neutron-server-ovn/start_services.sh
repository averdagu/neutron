#!/bin/bash

/usr/share/openvswitch/scripts/ovs-ctl start --system-id=random
/usr/share/ovn/scripts/ovn-ctl start_ovsdb --db-nb-create-insecure-remote=yes --db-sb-create-insecure-remote=yes
/usr/share/ovn/scripts/ovn-ctl start_northd
/usr/share/ovn/scripts/ovn-ctl start_controller

neutron-server --config-dir /mnt/host --config-file /mnt/host/neutron.conf --log-file /mnt/host/server.log &

server_pid=$!

trap "kill -15 $server_pid" SIGTERM

wait $server_pid
