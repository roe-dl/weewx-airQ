#!/usr/bin/python3
# Copyright (C) 2021 Johanna Roedenbeck
# WeeWX service to read data from the airQ device 

"""

Hardware: https://www.air-q.com

Science option ist required.


Most of the the observation types provided by the airQ device are
predefined within WeeWX. If no special configuration besides host
address and password is provided the measured values are stored to
those observation types. 

More than one device can be used. That is done by configurating a
specific prefix for the observation types of each device.

Configuration in weewx.conf:

[airQ]

    [[first_device]]
        host = replace_me_by_host_address_or_IP
        password = replace_me
        prefix = replace_me # optional
        
    [[second_device]]
        ...

"""

VERSION = 0.2

# imports for airQ
import base64
from Cryptodome.Cipher import AES
import http.client
import json

# deal with differences between python 2 and python 3
try:
    # Python 3
    import queue
except ImportError:
    # Python 2
    # noinspection PyUnresolvedReferences
    import Queue as queue

# imports for WeeW
import six
import threading
import time
if __name__ != '__main__':
    # for use as service within WeeWX
    import weewx
    from weewx.engine import StdService
    import weewx.units
    import weewx.accum
    import weeutil.weeutil
else:
    # for standalone testing
    import sys
    import collections
    sys.path.append('../../test')
    from testpasswd import airqIP,airqpass
    class StdService(object):
        def __init__(self, engine, config_dict):
            pass
        def bind(self,p1,p2):
            pass
    class weewx(object):
        NEW_LOOP_PACKET = 1
        class units(object):
            def convertStd(p1, p2):
                return p1
            obs_group_dict = collections.ChainMap()
            conversionDict = collections.ChainMap()
            default_unit_format_dict = collections.ChainMap()
            default_unit_label_dict = collections.ChainMap()
        class accum(object):
            accum_dict = collections.ChainMap()
    class weeutil(object):
        class weeutil(object):
            def to_int(x):
                return int(x)
    class Event(object):
        packet = { 'usUnits':16 }
        

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging
    log = logging.getLogger("user.air-Q")

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'user.air-Q: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)


ACCUM_LAST_DICT = { 'accumulator':'firstlast','extractor':'last' }

##############################################################################
#   add additional units needed for airQ                                     #
##############################################################################

# unit g/m^2 for 'group_concentration'
weewx.units.conversionDict.setdefault('microgram_per_meter_cubed',{})
weewx.units.conversionDict.setdefault('gram_per_meter_cubed',{})
weewx.units.conversionDict['gram_per_meter_cubed']['microgram_per_meter_cubed'] = lambda x : x*1000
weewx.units.conversionDict['microgram_per_meter_cubed']['gram_per_meter_cubed'] = lambda x : x*0.001
weewx.units.default_unit_format_dict.setdefault('gram_per_meter_cubed',"%.1f")
weewx.units.default_unit_label_dict.setdefault('gram_per_meter_cubed',u" g/m³")
# unit ppb for 'TVOC'
weewx.units.conversionDict.setdefault('ppb',{})
weewx.units.conversionDict.setdefault('ppm',{})
weewx.units.conversionDict['ppb']['ppm'] = lambda x:x*0.001
weewx.units.conversionDict['ppm']['ppb'] = lambda x:x*1000

##############################################################################
#   get data out of the airQ device                                          #
##############################################################################

def airQreply(htmlreply, passwd):
    """ convert the reply to json """
    # the reply is a json string
    _rtn = json.loads(htmlreply)
    # 'content' is base64 encoded and encrypted data
    if 'content' in _rtn:
        # convert base64 to plain text
        _crtxt = base64.b64decode(_rtn['content'])
        # convert passwd to bytes
        _aeskey = passwd.encode('utf-8')
        # adjust to 32 bytes of length
        _aeskey = _aeskey.ljust(32,b'0')
        # decode AES256
        _cipher = AES.new(key=_aeskey, mode=AES.MODE_CBC, IV=_crtxt[:16])
        _txt = _cipher.decrypt(_crtxt[16:]).decode('utf-8')
        _rtn['content'] =  json.loads(_txt[:-ord(_txt[-1])])
    # reply converted to python dict with 'content' decoded
    return _rtn

def airQget(connection, page, passwd):
    """ get page from airQ """
    try:
        connection.request('GET', page)
        _response = connection.getresponse()
        if _response.status==200:
            # successful --> get response
            reply = airQreply(_response.read(), passwd)
        else:
            # HTML error
            reply = {'content':{}}
        reply['replystatus'] = _response.status
        reply['replyreason'] = _response.reason
        reply['replyexception'] = ""
    except http.client.HTTPException as e:
        reply = {
            'replystatus': 400,
            'replyreason': "HTTPException %s" % e,
            'replyexception': "HTTPException",
            'content': {}}
    except OSError as e:
        # device not found
        reply = {
            'replystatus': 404,
            'replyreason': "OSError %s" % e,
            'replyexception': "OSError",
            'content': {}}
    return reply

##############################################################################
#    Thread to retrieve data from the air-Q device                           #
##############################################################################

class AirqThread(threading.Thread):
    """ retrieve data from airQ device """
    
    def __init__(self, q, name, address, passwd, log_success, log_failure):
        """ initialize thread """
        super(AirqThread,self).__init__()
        self.queue = q
        self.name = name
        self.address = address
        self.passwd = passwd
        self.log_success = log_success
        self.log_failure = log_failure
        self.running = True
        
    def shutdown(self):
        """ stop thread """
        self.running = False
        
    def run(self):
        """ run thread """
        loginf("thread '%s', host '%s': starting" % (self.name,self.address))
        connection = http.client.HTTPConnection(self.address)
        errsleep = 60
        while self.running:
            reply = airQget(connection, '/data', self.passwd)
            if reply['replystatus']==200:
                if errsleep:
                    if self.log_success:
                        loginf("thread '%s', host '%s': %s - %s" % (self.name,self.address,reply['replystatus'],reply['replyreason']))
                    errsleep = 0
                self.queue.put(reply['content'])
                time.sleep(1.5)
            else:
                if self.log_failure:
                    logerr("thread '%s', host '%s': %s - %s" % (self.name,self.address,reply['replystatus'],reply['replyreason']))
                # in case of repeated errors, close connection
                if reply['replyexception']=="HTTPException" or errsleep>240: 
                    connection.close()
                # wait
                time.sleep(errsleep)
                # in case of repeated errors, re-open connection
                if reply['replyexception']=="HTTPException" or errsleep>240: 
                    connection = http.client.HTTPConnection(self.address)
                if errsleep<300: errsleep+=60
        connection.close()
        loginf("thread '%s', host '%s': stopped" % (self.name,self.address))
            

##############################################################################
#   WeeWX service for airQ device                                            #
##############################################################################

class AirqService(StdService):

    AIRQ_DATA = {
        'DeviceID':    ('airqDeviceID',    None,None,lambda x:x),
        'Status':      ('airqStatus',      None,None,lambda x:x),
        'timestamp':   None,
        'measuretime': ('airqMeasuretime', None, None, lambda x:int(x)),
        'uptime':      ('airqUptime',      None, None, lambda x:int(x)),
        'temperature': ('airqTemp',        'degree_C',                  'group_temperature',lambda x:float(x[0])),
        'humidity':    ('airqHumidity',    'percent', 'group_percent',lambda x:x[0]),
        'humidity_abs':('airqHumAbs',      'gram_per_meter_cubed', 'group_concentration', lambda x:float(x[0])),
        'dewpt':       ('airqDewpoint',    'degree_C',                  'group_temperature',lambda x:float(x[0])),
        'pressure':    ('airqPressure',    'mbar',                      'group_pressure',lambda x:float(x[0])),
        'co':          ('co',              'milligram_per_meter_cubed', 'group_concentration',lambda x:x[0]),
        'co2':         ('co2',             'ppm',                       'group_fraction',lambda x:x[0]),
        'h2s':         ('h2s',             "microgram_per_meter_cubed", "group_concentration",lambda x:x[0]),
        'no2':         ('no2',             "microgram_per_meter_cubed", "group_concentration",lambda x:x[0]),
        'pm1':         ('pm1_0',           "microgram_per_meter_cubed", "group_concentration",lambda x:x[0]),
        'pm2_5':       ('pm2_5',           "microgram_per_meter_cubed", "group_concentration",lambda x:x[0]),
        'pm10':        ('pm10_0',          "microgram_per_meter_cubed", "group_concentration",lambda x:x[0]),
        'o3':          ('o3',              "microgram_per_meter_cubed", "group_concentration",lambda x:x[0]),
        'so2':         ('so2',             "microgram_per_meter_cubed", "group_concentration",lambda x:x[0]),
        'tvoc':        ('TVOC',            'ppb',                       'group_fraction',lambda x:x[0]),
        'oxygen':      ('o2',              'percent', 'group_percent',lambda x:x[0]),
        'sound':       ('noise',           'dB',                        'group_db', lambda x:x[0]),
        'performance': ('airqPerfIdx',     None, None, lambda x:float(x)/10),
        'health':      ('airqHealthIdx',   None, None, lambda x:x/10),
        'cnt0_3':      ('cnt0_3',          'count', 'group_count', lambda x:int(x[0])),
        'cnt0_5':      ('cnt0_5',          'count', 'group_count', lambda x:int(x[0])),
        'cnt1':        ('cnt1_0',          'count', 'group_count', lambda x:int(x[0])),
        'cnt2_5':      ('cnt2_5',          'count', 'group_count', lambda x:int(x[0])),
        'cnt5':        ('cnt5_0',          'count', 'group_count', lambda x:int(x[0])),
        'cnt10':       ('cnt10_0',         'count', 'group_count', lambda x:int(x[0])),
        'TypPS':       ('TypPS',           None, None, lambda x:x),
        'bat':         ('airqBattery',     None, None, lambda x:x),
        'door_event':  ('airqDoorEvent',   None, None, lambda x:int(x))
        }
        
    AVG_GROUPS = [
        'group_temperature',
        'group_concentration',
        'group_fraction']
        
    ACCUM_LAST = [
        'DeviceID',
        'Status',
        'bat']
        
    def __init__(self, engine, config_dict):
        super(AirqService,self).__init__(engine, config_dict)
        loginf("air-Q %s" % VERSION)
        # logging configuration
        self.log_success = config_dict.get('log_success',True)
        self.log_failure = config_dict.get('log_failure',True)
        self.debug = weeutil.weeutil.to_int(config_dict.get('debug',0))
        if self.debug>0:
            self.log_success = True
            self.log_failure = True
        # dict of devices and threads
        self.threads={}
        # devices
        ct = 0
        if 'airQ' in config_dict:
            for device in config_dict['airQ']:
                if self._create_thread(device,
                    config_dict['airQ'][device].get('host'),
                    config_dict['airQ'][device].get('password'),
                    config_dict['airQ'][device].get('prefix')):
                    ct+=1
            if ct>0:
                self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        if ct==1:
            loginf("1 air-Q device found")
        else:
            loginf("%s air-Q devices found" % ct)

    def _create_thread(self, thread_name, address, passwd, prefix):
        if address is None or address=='': 
            logerr("device '%s': not host address defined" % thread_name)
            return False
        if passwd is None or passwd=='':
            logerr("device '%s': no password defined" % thread_name)
            return False
        self.threads[thread_name] = {}
        self.threads[thread_name]['queue'] = queue.Queue()
        self.threads[thread_name]['thread'] = AirqThread(self.threads[thread_name]['queue'], thread_name, address, passwd, self.log_success, self.log_failure)
        self.threads[thread_name]['prefix'] = prefix
        self.threads[thread_name]['thread'].start()
        loginf("device '%s' host address '%s'" % (thread_name,address))
        # set accumulators for non-numeric observation types
        _accum = {}
        for ii in self.ACCUM_LAST:
            _obs_conf = self.AIRQ_DATA[ii]
            if _obs_conf:
                _accum[self.obstype_with_prefix(_obs_conf[0],prefix)] = ACCUM_LAST_DICT
            else:
                _accum[self.obstype_with_prefix(ii,prefix)] = ACCUM_LAST_DICT
        weewx.accum.accum_dict.maps.append(_accum)
        # set units for observation types
        for ii in self.AIRQ_DATA:
            _obs_conf = self.AIRQ_DATA[ii]
            if _obs_conf and _obs_conf[2] is not None:
                weewx.units.obs_group_dict.setdefault(self.obstype_with_prefix(_obs_conf[0],prefix),_obs_conf[2])
        return True
            
    def shutdown(self):
        for ii in self.threads:
            loginf("shutting down connection to '%s'" % ii)
            self.threads[ii]['thread'].shutdown()
        
    def new_loop_packet(self, event):
        for ii in self.threads:
            data = {}
            avg_sum = {}
            avg_ct = {}
            last_ts = 0
            while True:
                try:
                    # get new data packet from queue
                    reply = self.threads[ii]['queue'].get(block=False)
                    # check timestamp
                    if reply['timestamp']<=last_ts: continue
                    # check status
                    try:
                        if reply.get('Status','')=='OK':
                            airqstate = {}
                        else:
                            airqstate = json.loads(reply['Status'])
                            if 'Status' in airqstate:
                                airqstate = airqstate['Status']
                    except (KeyError,ValueError,IndexError,TypeError):
                        airqstate = {}
                    # process values
                    for jj in reply:
                        try:
                            unit_group = self.AIRQ_DATA.get(jj)[2] 
                        except (IndexError,TypeError):
                            unit_group = ""
                        if jj in airqstate:
                            # observation type is mentioned in status,
                            # that means the value is invalid
                            val = None
                        else:
                            # otherwise try to get the value
                            try:
                                xx = self.AIRQ_DATA.get(jj)
                                val = xx[3](reply[jj]) if xx is not None else reply[jj]
                            except (ValueError,TypeError,IndexError,KeyError) as e:
                                val = None
                        #logdbg("val %s - %s - %s" % (jj,reply[jj],val))
                        if unit_group in self.AVG_GROUPS:
                            # if observation type is in AVG_GROUPS, then
                            # add values for calculating averages
                            if val:
                                avg_sum[jj] = avg_sum.get(jj,0)+val
                                avg_ct[jj] = avg_ct.get(jj,0)+1
                        else:
                            # otherwise remember the last value of the
                            # loop period
                            data.update({jj:val})
                except queue.Empty:
                    break
                except KeyError:
                    # instead of queue.Empty KeyError was raised
                    break
                except (IndexError,ValueError,TypeError) as e:
                    logerr("new_loop_packet %s" % e)
            # calculate average
            for jj in avg_sum:
                data.update({jj:avg_sum[jj]/avg_ct[jj]})
            # convert airQ to WeeWX observation type names and
            # values to archive unit system
            data = self.airq_to_weewx(data, self.threads[ii].get('prefix'), event.packet.get('usUnits'))
            # 'dateTime' and 'interval' must not be in data
            if data.get('dateTime'): del data['dateTime']
            if data.get('interval'): del data['interval']
            # update loop packet with airQ data
            event.packet.update(data)

    '''
    @staticmethod
    def get_airq_value(val):
        """ get the real value out of the json value """
        try:
            iter(val)
            if len(val)==2 and not isinstance(val,six.string_types):
                return val[0]
        except TypeError:
            pass
        return val
    '''    
    
    @staticmethod
    def obstype_with_prefix(obs_type,prefix):
        """ prepend prefix if given """
        return prefix + '_' + obs_type.replace('airq','') if prefix else obs_type
    
    def airq_to_weewx(self, data, prefix, usUnits):
        """ convert field names """
        _data = {}
        for key in data:
            val = data[key]
            # adapt name and convert value
            if key in self.AIRQ_DATA:
                # if no value tuple is given, ignore that key
                if self.AIRQ_DATA[key] is None: continue
                # get the WeeWX observation type
                weewx_key = self.AIRQ_DATA[key][0]
                # if unit and unit group are given, convert to archive unit
                if self.AIRQ_DATA[key][1]:
                    try:
                        val = weewx.units.convertStd(
                            (val, self.AIRQ_DATA[key][1], self.AIRQ_DATA[key][2]),
                            usUnits)[0]
                    except (ValueError,KeyError,IndexError):
                        val = None
            else:
                # if key not in self.AIRQ_DATA use value as is
                weewx_key = key
            # if prefix is set prepend key with prefix
            weewx_key = self.obstype_with_prefix(weewx_key,prefix)
            #if prefix: weewx_key = prefix + '_' + weewx_key.replace('airq','')
            _data[weewx_key] = val
        return _data


    
# To test the service, run it directly as follows:
if __name__ == '__main__':
    if False:
        connection = http.client.HTTPConnection(airqIP)
        reply = airQget(connection, '/data', airqpass) 
        connection.close()
        print("Status {} - {}".format(reply['replystatus'],reply['replyreason']))
        #print(reply['content'])
        for ii in reply['content']:
            print("%15s: %s" % (ii,reply['content'][ii]))
    else:
        CONF = {
            'airQ': {
                '1': {
                    'host':airqIP,
                    'password':airqpass
                    }
                }
            }
        srv = AirqService({},CONF)
        print("weewx.accum.accum_dict = ")
        print(weewx.accum.accum_dict)
        print("weewx.units.conversionDict =")
        print(weewx.units.conversionDict)
        print("-----------")
        for jj in range(1):
            time.sleep(11)
            evt = Event()
            srv.new_loop_packet(evt)
            for ii in evt.packet:
                print("%15s: %s" % (ii,evt.packet[ii]))
            print("------------")
        srv.shutdown()
        
