#!/bin/bash

# Create the log files
touch /var/log/cron.log
touch /var/log/sampling.log
touch /var/log/sync.log
touch /var/log/process.log

# Start cron daemon
cron

# Follow the logs to keep the container running
tail -f /var/log/cron.log