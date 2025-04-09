#!/bin/sh
cd "$(dirname "$0")";
CWD="$(pwd)"
echo $CWD
echo "Commencing bash script" >> /home/atomsk/git/tuberipper/tuberipper.log
. venv/bin/activate
python3 tuberipper.py






