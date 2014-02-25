#!/bin/bash
eval $(ssh-agent)
ssh-add ~/.ssh/citrix_gerrit
/usr/local/bin/osci-manage -v
