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
/usr/local/bin/osci-view failures >> $CI_DIR/all_failures.txt

/usr/local/bin/osci-upload $CI_DIR ci_status
