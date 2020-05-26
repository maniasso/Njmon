#!/bin/bash
for i in $(cat /njmon/hmclist)
do
/njmon/nmon2influxdb hmc import --hmc $i
done
