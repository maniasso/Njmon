#!/usr/bin/python3
# import socket programming library
'''njmond.py opens a socket from remote njmon stats agents and injects the data in to InfluxDB'''
import socket
import queue
import sys
from sys import argv
import string
import json
import time
import multiprocessing
import argparse
from datetime import datetime
from influxdb import InfluxDBClient
# import thread module
from _thread import *
#import threading

worker_id = 0
queue = multiprocessing.Queue()

def logger(string1, string2):
    '''Append log information and error to the njmond log file'''
    global config
    
    log_file = config["directory"] + "njmond.log"
    if string1 == "DEBUG" and config["debug"] is False:
        return

    with open(log_file, 'a') as logfile:
        timestr = datetime.now()
        logfile.write(str(timestr)+': '+string1 + ":" + string2 + "\n")
    return

def thread_stats():
    '''Output stats regardng threads'''
    global queue

    queue_warning = 20
    logger('INFO', 'Statistics Thread started')
    while True:
        time.sleep(10)
        if queue.qsize() > queue_warning:
            logger('WARNING', ' Queue length='+str(queue.qsize())+ " Warning size=" + str(queue_warning))

        logger('DEBUG', 'Queue length='+str(queue.qsize()))

def parse_worker(queue):
    '''This is one of the logger threads'''
    dbhost = "localhost"
    global config
    global worker_id

    clientdb = InfluxDBClient(config["influx_host"], 
                              config["influx_port"], 
                              config["influx_user"], 
                              config["influx_password"], 
                              config["influx_dbname"])
    logger('DEBUG', 'Worker id='+str(worker_id)+'started')

    entry = []
    taglist = {}
    serial_no = 'unknown'
    mtm = 'unknown'
    os_name = 'unknown'
    arch = 'unknown'

    while True:
        time.sleep(0.02)
        while not queue.empty():
            string = queue.get()
            logger("DEBUG", "Unqueue packet" + "length=%d"%(len(string)))
            try:
                sample = json.loads(string)
            except:
                logger("INFO", "JSON parse failure" + "length=%d"%(len(string)))
                logger("INFO", string)
                continue

            timestamp = sample["timestamp"]["UTC"]

            try:
                os_name = sample["config"]["OSname"]
                arch = sample["config"]["processorFamily"]
                mtm = sample["server"]["machine_type"]
                serial_no = sample["server"]["serial_no"]
                aix = True
            except: 
                # Not AIX imples Linux
                os_name = sample["os_release"]["name"]
                if os_name == "Red Hat Enterprise Linux":
                    os_name = "RHEL"
                if os_name == "Red Hat Enterprise Linux Server":
                    os_name = "RHEL"
                if os_name == "SUSE Linux Enterprise Server":
                    os_name = "SLES"
                arch = "unknown"
                aix = False

            if aix is False:
                try:
                    # Linux under PowerVM
                    serial_no = sample['ppc64_lparcfg']['serial_number']
                    mtm = sample['ppc64_lparcfg']['system_type']
                except:
                    serial_no = "unknown"
                    mtm = "unknown"
            if arch == "unknown":
                try:
                    arch = sample['lscpu']['architecture']
                except:
                    arch = "unknown"
            if serial_no == "unknown":
                try:
                    serial_no = sample['identity']['serial-number']
                except:
                    serial_no = "unknown"
            if mtm == "unknown":
                try:
                    mtm = sample['identity']['model']
                except:
                    mtm = "unknown"

            try:
                mtm = mtm.replace('IBM,', '')
                serial_no = serial_no.replace('IBM,', '')
                host = sample['identity']['hostname']
                cookie = sample['identity']['cookie']
                snap = sample['timestamp']['snapshot_loop']
                njmonv = sample['identity']['njmon_version']
            except:
               continue

            logger("snapshot", "%d,%s,%s,%s,%s,%s,%d,%s"%(config["njmon_port"], host, os_name, arch, mtm, serial_no, snap, njmonv))
            if config["njmon_secret"] != "ignore":
                if config["njmon_secret"] != cookie:
                    logger("INFO","Cookie:Secret mismatch","%s:%s"%(config["njmon_secret"],cookie))
                    # IF YOU WANT TO REJECT BAD SECRETS UNCOMMENT THE BELOW CONTINUE
                    # contunue

            for section in sample.keys():
                logger ("DEBUG", "section" + section)
                for sub in sample[section].keys():
                    logger("DEBUG", "members are type" + str(type(sample[section][sub])))
                    if type(sample[section][sub]) is dict:
                        fieldlist = sample[section][sub]
                        measurename = str(section)
                        # Rename so all the cpu stats start "cpu..."
                        if measurename == "logical_cpu": measurename = "cpu_logical"
                        if measurename == "physical_cpu": measurename = "cpu_physical"
                        name = measurename
                        if name[-1] == "s": # has a training "s" like disks or networks
                            name = name[0:-1] + "_name" # remove the trailing "s"
                        else:
                            name = name + "_name"
                        taglist = {'host': host, 'os': os_name, 'architecture': arch, 'serial_no': serial_no, 'mtm': mtm, name: sub}
                        measure = {'measurement': measurename, 'tags': taglist, 'time': timestamp, 'fields': fieldlist}
                        entry.append(measure)
                    else:
                        fieldlist = sample[section]
                        measurename = str(section)
                        # Rename so all the cpu stats start "cpu..."
                        if measurename == "total_logical_cpu": measurename = "cpu_logical_total"
                        if measurename == "total_physical_cpu": measurename = "cpu_physical_total"
                        if measurename == "total_physical_cpu_spurr": measurename = "cpu_physical_total_spurr"
                        taglist = {'host': host, 'os': os_name, 'architecture': arch, 'serial_no': serial_no, 'mtm': mtm}
                        measure = {'measurement': measurename, 'tags': taglist, 'time': timestamp, 'fields': fieldlist}
                        entry.append(measure)
                        break

            try:
                if clientdb.write_points(entry) is False:
                    logger("DEBUG","WID="+str(worker_id)+", write.points() to Influxdb failed length="+str(len(entry)))
                    entry.clear()
                else:
                    logger("DEBUG", "WID="+str(worker_id)+",Injected snapshot for " + host)
                    entry.clear()
            except Exception as e:
                logger('ERROR ', 'WID='+str(worker_id)+'Error in write INFLUXDB: '+str(e))
                logger('ERROR', 'Total: '+entry)

    clientdb.close()

def clean_hostname(hostname):
    PERMITTED = "" + string.digits + string.ascii_letters + '_-.'
    safe = "".join(c for c in hostname if c in PERMITTED)
    return safe.replace('..','')

def threaded(conn):
    '''Get the message from the queue'''
    global config

    buffer = ""

    while True:
        try:
            data = conn.recv(655360)
            if not data:
                # zero length packets are silently ignored
                # logger('ERROR ','Read but no data in socket. Closing socket.')
                break
        except:
            logger('ERROR ', 'Error reading from socket.')
            break
        buffer = buffer + data.decode('utf-8')
        if buffer[-1:] != "\n":
            continue # not a complete JSON record so recv some more

        # Process buffer read from njmon client, parse json and insert into DB if packet is complete.
        if config["data_inject"]:
            queue.put(buffer)

        if config["data_json"]:
            try:
                sample = json.loads(buffer)
            except:
                logger('INFO', "Saving .json but record does not parse")
                logger('INFO', buffer)
                continue

            host = sample['identity']['hostname'] 
            #clean hostname
            json_file = config["directory"] + clean_hostname(host) + ".json"
            
            logger('DEBUG', "Opening file "+json_file)
            try:
                jsonfd = open(json_file, "a")
            except Exception as e:
                logger('ERROR', "Opening file "+json_file+". Error: "+str(e))

            try:
                jsonfd.write(buffer)
            except:
                logger('ERROR', 'Error writing to file: '+json_file)

            try:
                jsonfd.close()
            except:
                logger('ERROR', 'Error closing json file: '+json_file)
        buffer = ""

    logger('DEBUG', 'Exiting Thread')
    # socket connection closed
    conn.close()

def hints():
    print('njmond.py HELP Information - Version 50')
    print('Syntax:')
    print('    njmond.py configfile')
    print('')
    print('Sample config file - njmond.conf:')
    print('{')
    print('"njmon_port": 8181,')
    print('"njmon_secret": "0xdeadbeef",')
    print('"data_inject": true,')
    print('"data_json": false,')
    print('"directory": "/home/nigle/njmon",')
    print('"influx_host": "localhost",')
    print('"influx_port": 8086,')
    print('"influx_user": "nag",')
    print('"influx_password": "mypassWD",')
    print('"influx_dbname": "njmon",')
    print('"workers": 2,')
    print('"debug": false')
    print('}')
    print('')
    print('Note: workers=2 tested for 600++ endpoints at once a minute (max workers=32)')
    print('Note: if "inject": false then influx_ details are ignored"')
    print('Note: if "json": true then .json files placed in "diretory"')
    print('      Warning: json files are large = risk of filling the file system')
    print('      Recommend daily mv the files to archive dir and compress')
    print('Note: njmond.log created in "directory"')
    print('Note: debug just addes more details to the log')
    print('Note: if "njmon_secret": "ignore" then secrets from njmon are not checked')
    sys.exit(6)

 
def Main():
    '''main code starts here'''
    global config
    global worker_id

    # config file parsing
    try:
        configfile = argv[1]
    except:
        print("Missing configfile argument: njmond.py njmod.conf")
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
        return 20

    try:
        config = json.loads(configs)
    except:
        print("Failed to parse JSON within njmond config file")
        return 21

    print(config)
    try:
        number = config["njmon_port"]
    except:
        config["njmon_port"] = 8181
        print("using default njmon_port 8181")

    try:
        string = config["njmon_secret"]
    except:
        config["njmon_secret"] = "ignore"
        print("using default njmon_secret ignore")

    try:
        mybool  = config["data_inject"]
    except:
        config["data_inject"] = True
        print("using default data_inject true")

    try:
        mybool  = config["data_json"]
    except:
        config["data_json"] = False
        print("using default data_json False")

    try:
        string  = config["directory"]
    except:
        config["directory"] = "."
        print("using default directory .")

    if config["data_inject"] == True:
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
            number = config["workers"]
        except:
            config["workers"] = 2
            print("using default workers 2")

    try:
        mybool = config["debug"]
    except:
        config["debug"] = False
        print("using default debug False2")

    # Sanity Check
    dir = config["directory"]
    if dir == '//' or \
       dir.startswith('/bin') or \
       dir.startswith('/tmp') or \
       dir.startswith('/dev') or \
       dir.startswith('/etc') or \
       dir.startswith('/lib') or \
       dir.startswith('/usr') or \
       dir.startswith('/sbin'):
        print('Not a good top directory %s (suggest /home/njmon or /var/njmon)'%(dir))
        return 32

    if not config["directory"].endswith("/"):
        config["directory"] = config["directory"] + "/"
    # now logger function will work

    if config["njmon_port"] < 0 or config["njmon_port"] > 60000:
        msg = 'Invalid port number '+port+'(try 1->60000)'
        print(msg)
        logger('ERROR:', msg)
        return 34

    if config["workers"] < 2 and config["workers"] > 32:
        msg = 'Injector workers can\'t less than 2 or exceed 32'
        print(msg)
        logger('ERROR:', msg)
        return 35

    logger('INFO', 'njmond v50')
    parse_workers_list = []
    nproc = 0

    while (nproc < config["workers"]):
        thisWorker = multiprocessing.Process(target=parse_worker, args=[queue])
        parse_workers_list.append(thisWorker)
        thisWorker.start()
        nproc = nproc + 1
        worker_id = worker_id + 1
    try:
       # set up the socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("0.0.0.0", config["njmon_port"]))
        # put the socket into listening mode
        sock.listen(250)
    except:
        logger('ERROR', "socket create, bind or listen failed")

    start_new_thread(thread_stats, ())

    # a forever loop until client wants to exit
    while True:

        # establish connection with njmon client
        conn, addr = sock.accept()

        # Start a new thread and return its identifier
        start_new_thread(threaded, (conn,))

if __name__ == '__main__':
    Main()
