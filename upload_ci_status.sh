#!/bin/bash
set -eux

CI_DIR=/tmp/ci_status

[ -e $CI_DIR ] && rm -rf $CI_DIR
mkdir -p $CI_DIR

set +u
. /opt/osci/env/bin/activate
set -u

date > $CI_DIR/current_queue.txt
osci-view list --states Running,Queued,Collecting >> $CI_DIR/current_queue.txt
date > $CI_DIR/recent_finished.txt
osci-view list --states Collected,Finished --recent 24 >> $CI_DIR/recent_finished.txt
date > $CI_DIR/all_failures.txt
osci-view failures --recent 168 >> $CI_DIR/all_failures.txt

# Upload to the "status" container so the CDN will refresh every 15 minutes
osci-upload -c status $CI_DIR ci_status
