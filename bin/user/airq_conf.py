#!/usr/bin/env python3
#
#    config tool for using airQ device with WeeWX
#
#    Copyright (C) 2021 Johanna Roedenbeck
#    WeeWX functions Copyright (C) 2009-2021 Tom Keffer
#    airQ API Copyright (C) Corant GmbH

from __future__ import absolute_import
from __future__ import print_function
from __future__ import with_statement

# modules for WeeWX access
import weewx
import weecfg.database
from weeutil.weeutil import y_or_n

import user.airQ_corant
import configobj
import optparse

# modules for airQ access
import base64
from Cryptodome.Cipher import AES
import http.client
from Cryptodome import Random
import json

import six

usage = """airq_conf --help
       airq_conf --device=DEVICE --print-config
       airq_conf --device=DEVICE --add-columns
       airq_conf --device=DEVICE --drop-columns
       airq_conf --device=DEVICE --set-location=station
       airq_conf --device=DEVICE --set-location=LATITUDE,LOGITUDE
       airq_conf --device=DEVICE --set-roomsize=HEIGHT,AREA
       airq_conf [--device=DEVICE] --set-ntp=NTP_SERVER"""
        
epilog = """NOTE: MAKE A BACKUP OF YOUR DATABASE BEFORE USING THIS UTILITY!
Many of its actions are irreversible!"""

headers = {'Content-type': 'application/x-www-form-urlencoded'}

NTP_SERVERS = {
    'default':'pool.ntp.org',
    'ntp':'pool.ntp.org',
    'de':'ptbtime3.ptb.de',
    'ptb':'ptbtime3.ptb.de'}
    
def airQrequest(data, passwd):
    data = json.dumps(data)
    _aeskey = passwd.encode('utf-8')
    _aeskey = _aeskey.ljust(32,b'0')
    # Erster Schritt: AES256 verschlüsseln
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key=_aeskey, mode=AES.MODE_CBC, IV=iv)
    msg = data.encode('utf-8')
    length = 16-(len(msg)%16)
    crypt = iv + cipher.encrypt(msg+chr(length).encode('utf-8')*length)
    # Zweiter Schritt: base64 enkodieren
    msgb64 = base64.b64encode(crypt).decode('utf-8')
    return msgb64

def airQput(host, page, passwd, data):
    try:
        connection = http.client.HTTPConnection(host)
        connection.request("POST", page, "request="+airQrequest(data,passwd),headers)
        _response = connection.getresponse()
        if _response.status==200:
            reply = user.airQ_corant.airQreply(_response.read(), passwd)
        else:
            reply = {'content':{}}
    except Exception as e:
        print(e)
        reply = None
    finally:
        connection.close()
    return reply



def main():

    # Create a command line parser:
    parser = optparse.OptionParser(usage=usage, epilog=epilog)
    
    # options
    
    parser.add_option("--device", type=str, metavar="DEVICE",
                       help="airQ device as defined in weewx.conf")
                       
    parser.add_option("--config", dest="config_path", type=str,
                      metavar="CONFIG_FILE",
                      help="Use configuration file CONFIG_FILE.")

    parser.add_option("--binding", metavar="BINDING_NAME", default='wx_binding',
                      help="The data binding to use. Default is 'wx_binding'.")
    
    # commands
                      
    parser.add_option("--print-config", action="store_true",
                      help="Get the config from the airQ device and print")
                      
    parser.add_option("--add-columns",action="store_true",
                       help="add columns to the WeeWX database")
                       
    parser.add_option("--drop-columns",action="store_true",
                       help="drop columns from the WeeWX database")

    parser.add_option("--set-location", dest="location", type=str, metavar="LOCATION",
                      help="write location into the airQ device")
                     
    parser.add_option("--set-roomsize", dest="roomsize", type=str, metavar="HEIGHT,AREA",
                      help="write room height and room area into the airQ device")
                      
    parser.add_option("--set-ntp", dest="ntp", type=str, metavar="NTP_SERVER",
                      help="write NTP server address to use into the airQ device")
    
    (options, args) = parser.parse_args()
    
    # get config_dict to use
    config_path, config_dict = weecfg.read_config(options.config_path, args)
    print("Using configuration file %s" % config_path)

    action_add = options.add_columns
    if action_add is None: action_add = False
    action_drop = options.drop_columns
    if action_drop is None: action_drop = False
    device = options.device
    db_binding = options.binding

    if options.print_config:
        printConfig(config_path,config_dict,device)
    elif options.location:
        setLocation(config_dict,device,options.location)
    elif options.roomsize:
        setRoomsize(config_dict,device,options.roomsize)
    elif options.ntp:
        setNTP(config_dict,device,options.ntp)
    else:
        addDropColumns(config_dict, db_binding, device, action_add, action_drop)


def printConfig(config_path,config_dict, device):
    """ retrieve config data from device and print to stdout """
    if device:
        conf = config_dict.get('airQ',{}).get(device)
        if conf is None:
            print("device '%s' not found in '%s'" % (device,config_path))
        else:
            host = conf.get('host')
            passwd = conf.get('password')
            print("requesting data...")
            reply = user.airQ_corant.airQget(host,"/config",passwd)
            print("config of device '%s' in '%s', host '%s', prefix '%s'" % (device,config_path,host,conf.get('prefix')))
            _printDict(reply['content'],0)
    else:
        conf = config_dict.get('airQ',{})
        for dev in conf:
            if isinstance(conf[dev],dict) and 'host' in conf[dev] and 'password' in conf[dev]:
                printConfig(config_path,config_dict,dev)
                print()

def _printDict(reply, indent):
    """ print dict with indent """
    for key in reply:
        if isinstance(reply[key],dict):
            print(' '*indent+"%s:" % key)
            _printDict(reply[key],indent+4)
        else:
            print(' '*indent+"%s: %s" % (key,reply[key]))
            
def addDropColumns(config_dict, db_binding, device, action_add, action_drop):
    """ prepare WeeWX database for airQ columens """
    if action_add and action_drop:
        # columns can be added or dropped but not both
        print("one of '--add-columns' or '--drop-columns' is possible only")
    elif not action_add and not action_drop:
        # add or drop?
        print("'--add-columns' or '--drop-columns' is needed")
    else:
        # action is defined, check device
        if device:
            # observeration types
            airq_data = user.airQ_corant.AirqService.AIRQ_DATA
            # weewx
            conf =  config_dict.get('airQ',{}).get(device)
            if conf is None:
                # device 'device' not defined in weewx.conf
                print("device '%s' not found in '%s'" % (device,config_path))
            else:
                prefix = conf.get('prefix',None)
                # what action
                if action_add:
                    print("Adding columns for device '%s', prefix '%s'" % (device,prefix))
                elif action_drop:
                    print("Dropping columns for device '%s', prefix '%s'" % (device,prefix))
                # columns of the original schema
                manager_dict = weewx.manager.get_manager_dict_from_config(
                                                  config_dict,db_binding)
                schema = manager_dict.get('schema',{}).get('table',{})
                # determine columns to add or drop
                cols = []
                ocls = []
                for ii in airq_data:
                    if airq_data[ii] is not None and airq_data[ii][0] is not None and ii not in user.airQ_corant.AirqService.ACCUM_LAST:
                        __col = user.airQ_corant.AirqService.obstype_with_prefix(airq_data[ii][0],prefix)
                        if __col in [col[0] for col in schema]:
                            ocls.append(__col)
                        else:
                            cols.append(__col)
                print()
                if action_add:
                    print("Columns to add:")
                elif action_drop:
                    print("Columns to drop:")
                print(cols)
                if len(ocls)>0:
                    print()
                    print("Omitted columns:")
                    print(ocls)
                    print("Those columns are in the database schema used "
                          "when the WeeWX database was created. So they cannot "
                          "be changed by the airQ configuration tool.")
                print()
                ans = y_or_n("Are you sure you want to proceed (y/n)?")
                if ans=='y':
                    if action_add:
                        addColumns(config_dict,db_binding,cols)
                    elif action_drop:
                        dropColumns(config_dict,db_binding,cols)
                    else:
                        print("invalid action")
                else:
                    print("Aborted. Nothing changed.")
                

        else:
            print("option '--device=DEVICE' is mandatory")


def addColumns(config_dict, db_binding, cols):
    """ add columns for the airQ device to the WeeWX database """
    column_type = 'REAL'
    dbm = weewx.manager.open_manager_with_config(config_dict, db_binding)
    for column_name in cols:
        dbm.add_column(column_name, column_type)
        print("New column %s of type %s added to database." % (column_name, column_type))

def dropColumns(config_dict, db_binding, cols):
    """ drop columns for the airQ device from the WeeWX database """
    drop_set = set(cols)
    dbm = weewx.manager.open_manager_with_config(config_dict, db_binding)
    # Now drop the columns. If one is missing, a NoColumnError will be raised. Be prepared
    # to catch it.
    try:
        print("This may take a while...")
        dbm.drop_columns(drop_set)
    except weedb.NoColumnError as e:
        print(e, file=sys.stderr)
        print("Nothing done.")
    else:
        print("Column(s) '%s' dropped from the database" % ", ".join(cols))


def setLocation(config_dict, device, loc):
    """ set location """
    if loc=="station":
        stn_info = config_dict.get('Station',{})
        lat = float(stn_info.get('latitude'))
        lon = float(stn_info.get('longitude'))
    else:
        _loc = loc.split(',')
        lat = float(_loc[0])
        lon = float(_loc[1])
    data = { 'geopos': { 'lat':lat, 'long':lon }}
    setConfig(config_dict, device, data)

def setRoom(config_dict, device, roomsize):
    """ set room size parameters """
    _size = roomsize.split(',')
    data = { 'RoomHeight':float(_size[0]),'RoomArea':float(_size[1]) }
    setConfig(config_dict, device, data)

def setNTP(config_dict, device, ntp):
    """ set NTP server for the airQ device """
    if ntp.lower() in NTP_SERVERS:
        ntp = NTP_SERVERS[ntp.lower()]
    data = { 'TimeServer': ntp }
    if device:
        setConfig(config_dict, device, data)
    else:
        conf = config_dict.get('airQ',{})
        for dev in conf:
            if isinstance(conf[dev],dict) and 'host' in conf[dev] and 'password' in conf[dev]:
                setConfig(config_dict, dev, data)

def setConfig(config_dict, device, data):
    """ write config data into the airQ device """
    if device:
        conf = config_dict.get('airQ',{}).get(device)
        if conf is None:
            print("device '%s' not found in '%s'" % (device,config_path))
        else:
            print("device '%s' host '%s' set %s" % (device,conf['host'],data))
            ans = y_or_n("Are you sure you want to proceed (y/n)?")
            if ans=='y':
                reply = airQput(conf['host'],"/config",conf['password'],data)
                _printDict(reply,0)
    else:
        print("option --device=DEVICE missing")

     
if __name__ == "__main__":
    main()

