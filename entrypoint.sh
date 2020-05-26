#!/bin/bash

# Start the run once job.
echo "Docker container has been started"

declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /container.env

# Setup a cron schedule
echo "SHELL=/bin/bash
BASH_ENV=/container.env
#*/20 * * * * /njmon/hmc_collector.sh >> /var/log/cron.log 2>&1
00 00 * * * cat /dev/null > /njmon/njmond.log
00 00 * * * cat /dev/null > /var/log/cron.log
# This extra line makes it a valid cron" > scheduler.txt

crontab scheduler.txt
#crond 

#Start supervisor.d
/usr/bin/supervisord -n
