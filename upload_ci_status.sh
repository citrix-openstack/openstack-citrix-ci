#!/bin/bash

TOP_DIR=$(cd $(dirname "$0") && pwd)

date > /tmp/current_queue.txt
$TOP_DIR/manage_openstack_gerrit.py --list --states Running,Queued >> /tmp/current_queue.txt
date > /tmp/recent_finished.txt
$TOP_DIR/manage_openstack_gerrit.py --list --states Collected,Finished --recent 24 >> /tmp/recent_finished.txt
date > /tmp/all_failures.txt
$TOP_DIR/manage_openstack_gerrit.py --failures >> /tmp/all_failures.txt

key=`awk '/SFTP_KEY/{print $3}' osci/config.py | tr -d "'" | tr -d '"'`

scp -i $key /tmp/current_queue.txt /tmp/all_failures.txt /tmp/recent_finished.txt \
    svcacct_openstack@int-ca.downloads.xensource.com:/var/www/html/ca.downloads.xensource.com/OpenStack/xenserver-ci/

