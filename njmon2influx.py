#!/usr/bin/python3
# This takes njmon v50+ output JSON files or direct pipe or socket and uploads the stats into InfluxDB
# NOTE DO NOT CHANGE THIS FILE
# The njmond.conf file can be used to set the InfluxDB conf 
#      One Parameneter is for the njmon2influx.py = batch
# ./njmon2influx.pg njmonb.conf <myserver.json

import sys
from sys import argv
import json
import datetime

def hints():
    print('njmond2influx.py HELP Information - Version 50')
    print('Syntax:')
    print('    cat myjsonfile.json | ./njmond2influx.py njmond.conf')
    print('    or')
    print('    ./njmond2influx.py njmond.conf <myjsonfile.json ')
    print('')
    print('Sample config file - njmond.conf:')
    print('{')
    print('"influx_host": "localhost",')
    print('"influx_port": 8086,')
    print('"influx_user": "nag",')
    print('"influx_password": "mypassWD",')
    print('"influx_dbname": "njmon",')
    print('"batch": 100')
    print('}')
    print('')
    sys.exit(6)


# config file parsing
try:
    configfile = argv[1]
except:
    print("Missing configfile argument: njmonstream njmod.conf")
    hints()

if configfile == "-h" or configfile == "-?" or configfile == "help":
    hints()
# read the conf file removing lise starting with #
try:
    configs = ""
    with open(configfile,"r") as f:
        for line in f:
            if line[0] == '#':
                pass
            else:
                configs = configs + line
except:
    print("Failed to read njmond config file:"+str(configfile))
    sys.exit(20)

try:
    config = json.loads(configs)
except:
    print("Failed to parse JSON within njmond config file")
    sys.exit(21)

print(config)

try:
    string  = config["influx_host"]
except:
    config["influx_host"] = "localhost"
    print("using default influx_host localhost")

try:
    number = config["influx_port"]
except:
    config["influx_port"] = 8086
    print("using default influx_port 8086")

try:
    string  = config["influx_user"]
except:
    print("Missing influx_user name in the conf file")
    sys.exit(40)

try:
    string  = config["influx_password"]
except:
    print("Missing influx_user name in the conf file")
    sys.exit(40)

try:
    string  = config["influx_dbname"]
except:
    config["influx_dbname"] = "njmon"
    print("using default influx_dbname njmon")

try:
    number  = config["batch"]
except:
    config["batch"] = 1
    print("using default batch 1 = good for pipe or socket (for bulk batch file load try 100)")

try:
    dirs = config["directory"]
except:
    dirs = "./"
    print("using default directory ./")


def logger(string1,string2):
    with open(dirs + '/njmon2influx.log','a') as f:
        f.write(string1 + "," + string2 + "\n")
    return

taglist = {}
first_time = True
serial_no = 'NotKnown'
mtm = 'NotKnown'

def inject_snapshot(sample):
    global taglist
    global first_time
    global serial_no
    global mtm
    global os_name
    global arch
    global hostname

    timestamp = sample["timestamp"]["UTC"]

    if first_time == True:
        first_time = False

        hostname=sample["identity"]["hostname"]
        try:
            os_name = sample["config"]["OSname"]
            arch = sample["config"]["processorFamily"]
            mtm = sample["server"]["machine_type"]
            serial_no = sample["server"]["serial_no"]
        except: # Not AIX imples Linux
            os_name = sample["os_release"]["name"]
            if os_name == "Red Hat Enterprise Linux Server":
                os_name = "RHEL"
            if os_name == "SUSE Linux Enterprise Server":
                os_name = "SLES"
            arch = "unknown"
            # not AIX so try LInux
            try:            # Linux under PowerVM
                serial_no = sample['ppc64_lparcfg']['serial_number']
                mtm = sample['ppc64_lparcfg']['system_type']
            except:
                serial_no = "unknown"
                mtm = "unknown"

            try:
                serial_no = sample['identity']['serial-number']
            except:
                serial_no = "unknown"

            try:
                arch = sample['lscpu']['architecture']
            except:
                arch = "unknown"

            if mtm == "unknown":
                try:
                    mtm = sample['identity']['model']
                except:
                    mtm = "unknown"

        mtm    = mtm.replace('IBM,','')
        serial_no = serial_no.replace('IBM,','')

        if(config["batch"] > 1):
            print("hostname:%s"%(hostname))
            try:
                print("njmon_version:%s"%(sample["identity"]["njmon_version"]))
            except:
                print("njmon_version: not set");
            print("timestamp:%s"%(timestamp))
            print("os_name:%s"%(os_name))
            print("architecture:%s"%(arch))
            print("mtm: %s"%(mtm))
            print("serial_no: %s"%(serial_no))
    # end of first time

    for section in sample.keys():
        for sub in sample[section].keys():
            if type(sample[section][sub]) is dict:
                fieldlist = sample[section][sub]
                measurename = str(section)
                # Rename so all the cpu stats start "cpu..."
                #if measurename == "logical_cpu": measurename = "cpu_logical"
                #if measurename == "physical_cpu": measurename = "cpu_physical"
                name = measurename
                if name[-1] == "s": # has a training "s" like disks or networks
                    name = name[0:-1] + "_name" # remove the trailing "s"
                else:
                    name = name + "_name"
                taglist = {'host': hostname, 'os': os_name, 'architecture': arch, 'serial_no': serial_no, 'mtm': mtm, name: sub }
                measure = { 'measurement': measurename, 'tags': taglist, 'time': timestamp, 'fields': fieldlist }
                entry.append(measure)
            else:
                fieldlist = sample[section]
                measurename = str(section)
                # Rename so all the cpu stats start "cpu..."
                #if measurename == "total_logical_cpu": measurename = "cpu_logical_total"
                #if measurename == "total_physical_cpu": measurename = "cpu_physical_total"
                #if measurename == "total_physical_cpu_spurr": measurename = "cpu_physical_total_spurr"
                taglist = {'host': hostname, 'os': os_name, 'architecture': arch, 'serial_no': serial_no, 'mtm': mtm }
                measure = { 'measurement': measurename, 'tags': taglist, 'time': timestamp, 'fields': fieldlist }
                entry.append(measure)
                break
    return hostname

def push(host):
    if client.write_points(entry) == False:
        logger("write.points() to Influxdb failed length=", str(len(entry)))
        logger("FAILED ENTRY",entry)
    else:
        now = datetime.datetime.now()
        logger(now.strftime("%Y-%m-%d %H:%M:%S") + ",snap="  + str(count) + "," + host +",db=" + config["influx_dbname"] + ",json-size=" + str(bytes) + ",measure-size=", str(len(entry)))
        entry.clear()
    return

#  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# Login to InfluxDB
#  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
from influxdb import InfluxDBClient
print("host=%s port=%d user=%s password=%s dbname=%s"%(config["influx_host"], config["influx_port"], config["influx_user"], config["influx_password"], config["influx_dbname"]))

client = InfluxDBClient( config["influx_host"], config["influx_port"], config["influx_user"], config["influx_password"], config["influx_dbname"])

count = 0
pushs = 0
bytes = 0
cached = 0
entry = []

for line in sys.stdin:
    count = count + 1
    bytes = len(line)
    #print("count=%d linesize=%d pushs=%d bytes=%d" cached=%d%(count,len(line),pushs, bytes))   
    host = inject_snapshot(json.loads(line))
    if config["batch"] > 1:
        cached = cached + 1
        if cached == config["batch"]:
            pushs = pushs + 1
            push(host)
            cached = 0
    else:
        pushs = pushs + 1
        push(host)

if len(entry) >= 1:
	pushs = pushs + 1
	push(host) 

print("injected=%d records batchsize=%d pushes=%d"%(count,config["batch"],pushs))
