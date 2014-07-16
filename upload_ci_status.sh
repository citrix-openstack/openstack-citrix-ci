#!/bin/bash
set -eux

TOP_DIR=$(cd $(dirname "$0") && pwd)

CI_DIR=/tmp/ci_status

[ -e $CI_DIR ] && rm -rf $CI_DIR
mkdir -p $CI_DIR

date > $CI_DIR/current_queue.txt
/usr/local/bin/osci-view list --states Running,Queued,Collecting >> $CI_DIR/current_queue.txt
date > $CI_DIR/recent_finished.txt
/usr/local/bin/osci-view list --states Collected,Finished --recent 24 >> $CI_DIR/recent_finished.txt
date > $CI_DIR/all_failures.txt
/usr/local/bin/osci-view failures --recent 168 >> $CI_DIR/all_failures.txt

# Upload to the "status" container so the CDN will refresh every 15 minutes
/usr/local/bin/osci-upload -c status $CI_DIR ci_status
