#!/bin/bash
eval $(ssh-agent)
ssh-add ~/.ssh/citrix_gerrit
/home/ubuntu/src/openstack-citrix-ci/manage_openstack_gerrit.py -v
