#!/bin/bash
eval $(ssh-agent)
ssh-add ~/.ssh/citrix_gerrit
/home/ubuntu/src/openstack-citrix-ci/manage_openstack_gerrit.py -v -g 10.80.2.68 -u citrix_xenserver_ci