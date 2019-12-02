#!/bin/bash

/usr/share/openvswitch/scripts/ovs-ctl start --system-id=random

function stop {
    /usr/share/openvswitch/scripts/ovs-ctl stop
    killall ovn-controller
}

trap stop SIGTERM

echo "Createing ovn log directory"
mkdir /var/log/ovn

echo "Starting OVN controller"
ovn-controller unix:/var/run/openvswitch/db.sock -vconsole:emer -vsyslog:err -vfile:dbg --no-chdir --log-file=/var/log/ovn/ovn-controller.log --pidfile=/var/run/ovn/ovn-controller.pid --monitor
