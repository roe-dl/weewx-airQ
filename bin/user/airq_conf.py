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
import weedb

import user.airQ_corant
import configobj
import optparse
import os.path
import shutil

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
       airq_conf [--device=DEVICE] --set-ntp=NTP_SERVER
       airq_conf --create-skin"""
        
epilog = """NOTE: MAKE A BACKUP OF YOUR DATABASE BEFORE USING THIS UTILITY!
Many of its actions are irreversible!"""

headers = {'Content-type': 'application/x-www-form-urlencoded'}

NTP_SERVERS = {
    'default':'pool.ntp.org',
    'ntp':'pool.ntp.org',
    'de':'ptbtime3.ptb.de',
    'ptb':'ptbtime3.ptb.de'}

def obstype_with_prefix(obs_type, prefix):
    return user.airQ_corant.AirqService.obstype_with_prefix(obs_type,prefix)
    
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
    
    parser.add_option("--create-skin", action="store_true",
                      help="create a simple skin with all the devices configured")
                      
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
    elif options.create_skin:
        createSkin(config_path,config_dict, db_binding)
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
                try:
                    schema = manager_dict.get('schema',{}).get('table',[])
                except AttributeError:
                    schema = manager_dict.get('schema',[])
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


def enumColumns(config_dict, db_binding, cols):
    manager_dict = weewx.manager.get_manager_dict_from_config(
                                                  config_dict,db_binding)
    existing_cols = []
    with weewx.manager.Manager.open(manager_dict['database_dict']) as manager:
        for col in cols:
            try:
                manager.getSql("SELECT `%s` from %s LIMIT 1;" % (col,manager.table_name))
                existing_cols.append(col)
            except weedb.NoColumnError:
                pass
    return existing_cols


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


HTML_HEAD='''<!DOCTYPE html>
<html lang="%s">
  <head>
    <meta charset="UTF-8">
    <title>$station.location $page</title>
    <link rel="icon" type="image/png" href="favicon.ico" />
    <link rel="stylesheet" type="text/css" href="seasons.css"/>
    <script src="seasons.js"></script>
  </head>
  <body onload="setup();">
    <div id="title_bar">
      <div id="title">
        <h1 class="page_title">$station.location $page</h1>
        <p class="lastupdate">$current.dateTime</p>
      </div>
      <div id="reports">
        ID: $current.%s.raw
        <br/>
        $current.%s.raw
      </div>
    </div>
'''
HTML_FOOT='''
  </body>
</html>
'''

def _check_gettext(seasons_skin_path):
    """ check whether gettext """
    with open(os.path.join(seasons_skin_path,'index.html.tmpl')) as f:
        for line in f:
            i = line.find('gettext')
            if i>=0:
                c = line[i+7]
                if c in ('(','['): return c
    return '?'

def createSkin(config_path, config_dict, db_binding):
    """ create skin """
    sensors = {}
    obstypes = {}
    RoomTypes = {}
    for dev in config_dict['airQ'].sections:
        print("device '%s':" % dev)
        reply = user.airQ_corant.airQget(
                       config_dict['airQ'][dev]['host'],'/config',
                       config_dict['airQ'][dev]['password'])
        sensors[dev] = reply['content']['sensors']
        RoomTypes[dev] = reply['content'].get('RoomType')
        print("  sensors %s" % sensors[dev])
        cols = []
        for img in IMG_DICT:
            for obs in img[2]:
                cols.append(obstype_with_prefix(obs,config_dict['airQ'][dev].get('prefix')))
        obstypes[dev] = enumColumns(config_dict, db_binding, cols)
        print("  obstypes in database %s" % obstypes[dev])
    
    seasons_skin_path = os.path.join(config_dict['WEEWX_ROOT'],
                            config_dict['StdReport']['SKIN_ROOT'],
                            config_dict['StdReport']['SeasonsReport']['skin'])
    print("Seasons skin path: %s" % seasons_skin_path)
    airq_skin_path = os.path.join(config_dict['WEEWX_ROOT'],
                            config_dict['StdReport']['SKIN_ROOT'],
                            'airQ')
    print("airQ skin path:    %s" % airq_skin_path)
    seasons_lang = config_dict['StdReport']['SeasonsReport'].get('lang')
    print("Seasons skin lang: %s" % seasons_lang)
    gettext_style = _check_gettext(seasons_skin_path)
    if gettext_style=='(':
        print("gettext style: function")
    elif gettext_style=='[':
        print("gettext style: bracket")
    else:
        print("gettext style: unknown")
    if not os.path.isdir(airq_skin_path):
        os.mkdir(airq_skin_path)
        print("created '%s'" % airq_skin_path)
    else:
        print("'%s' already exists, contents will be overwritten" % airq_skin_path)
    print("copy seasons.css")
    shutil.copy(os.path.join(seasons_skin_path,'seasons.css'),airq_skin_path)
    print("copy seasons.js")
    shutil.copy(os.path.join(seasons_skin_path,'seasons.js'),airq_skin_path)
    print("copy favicon.ico")
    shutil.copy(os.path.join(seasons_skin_path,'favicon.ico'),airq_skin_path)
    #print("copy titlebar.inc")
    #shutil.copy(os.path.join(seasons_skin_path,'titlebar.inc'),airq_skin_path)
    if os.path.isdir(os.path.join(airq_skin_path,'font')):
        print("font directory already exists")
    else:
        print("create font directory")
        os.mkdir(os.path.join(airq_skin_path,'font'))
    for file in os.listdir(os.path.join(seasons_skin_path,'font')):
        print("copy %s" % file)
        shutil.copy(os.path.join(seasons_skin_path,'font',file),os.path.join(airq_skin_path,'font'))
    if os.path.isdir(os.path.join(airq_skin_path,'lang')):
        print("language directory already exists")
    else:
        print("create language directory")
        os.mkdir(os.path.join(airq_skin_path,'lang'))
    airq_skin_file = os.path.join(airq_skin_path,'skin.conf')
    with open(airq_skin_file,'w') as file:
        print("creating skin file '%s'" % airq_skin_file) 
        file.write("""###############################################################################
# AIRQ SKIN CONFIGURATION FILE                                                #
# Copyritht (c) 2021 Johanna Roedenbeck                                       #
# Copyright (c) 2018-2021 Tom Keffer <tkeffer@gmail.com> and Matthew Wall     #
# See the file LICENSE.txt for your rights.                                   #
###############################################################################

# The following section is for any extra tags that you want to be available in
# the templates

[Extras]
""")
        print("  writing section [CheetahGenerator]")
        file.write("""
###############################################################################

# The CheetahGenerator creates files from templates.  This section
# specifies which files will be generated from which template.

[CheetahGenerator]

    # Possible encodings include 'html_entities', 'strict_ascii', 'normalized_as
    # as well as those listed in https://docs.python.org/3/library/codecs.html#s
    encoding = html_entities

    [[SummaryByMonth]]

    [[SummaryByYear]]

    [[ToDate]]
        # Reports that show statistics "to date", such as day-to-date,
        # week-to-date, month-to-date, etc.
        
        [[[index]]]
            template = index.html.tmpl
""")
        for dev in config_dict['airQ'].sections:
            template_file = "%s.html.tmpl" % dev
            file.write("""        [[[%s]]]
            template = %s
""" % (dev,template_file))
        print("  writing section [CopyGenerator]")
        file.write("""
###############################################################################

# The CopyGenerator copies files from one location to another.

[CopyGenerator]

    # List of files to be copied only the first time the generator runs
    copy_once = seasons.css, seasons.js, favicon.ico, font/*.woff, font/*.woff2

    # List of files to be copied each time the generator runs
    # copy_always = index.html


""")
        print("  writing section [ImageGenerator]")
        file.write("""###############################################################################

# The ImageGenerator creates image plots of data.

[ImageGenerator]

    # This section lists all the images to be generated, what SQL types are to
    # be included in them, along with many plotting options. There is a default
    # for almost everything. Nevertheless, values for most options are included
    # to make it easy to see and understand the options.
    #
    # Fonts can be anything accepted by the Python Imaging Library (PIL), which
    # includes truetype (.ttf), or PIL's own font format (.pil). See
    # http://www.pythonware.com/library/pil/handbook/imagefont.htm for more
    # details.  Note that "font size" is only used with truetype (.ttf)
    # fonts. For others, font size is determined by the bit-mapped size,
    # usually encoded in the file name (e.g., courB010.pil). A relative path
    # for a font is relative to the SKIN_ROOT.  If a font cannot be found,
    # then a default font will be used.
    #
    # Colors can be specified any of three ways:
    #   1. Notation 0xBBGGRR;
    #   2. Notation #RRGGBB; or
    #   3. Using an English name, such as 'yellow', or 'blue'.
    # So, 0xff0000, #0000ff, or 'blue' would all specify a pure blue color.

    image_width = 500
    image_height = 180
    image_background_color = "#ffffff"

    chart_background_color = "#ffffff"
    chart_gridline_color = "#d0d0d0"

    # Setting to 2 or more might give a sharper image with fewer jagged edges
    anti_alias = 1

    top_label_font_path = font/OpenSans-Bold.ttf
    top_label_font_size = 14

    unit_label_font_path = font/OpenSans-Bold.ttf
    unit_label_font_size = 12
    unit_label_font_color = "#787878"

    bottom_label_font_path = font/OpenSans-Regular.ttf
    bottom_label_font_size = 12
    bottom_label_font_color = "#787878"
    bottom_label_offset = 3

    axis_label_font_path = font/OpenSans-Regular.ttf
    axis_label_font_size = 10
    axis_label_font_color = "#787878"

    # Options for the compass rose, used for progressive vector plots
    rose_label = N
    rose_label_font_path = font/OpenSans-Regular.ttf
    rose_label_font_size  = 9
    rose_label_font_color = "#222222"

    # Default colors for the plot lines. These can be overridden for
    # individual lines using option 'color'.
    chart_line_colors = "#4282b4", "#b44242", "#42b442", "#42b4b4", "#b442b4"

    # Default fill colors for bar charts. These can be overridden for
    # individual bar plots using option 'fill_color'.
    chart_fill_colors = "#72b2c4", "#c47272", "#72c472", "#72c4c4", "#c472c4"

    # Type of line. Options are 'solid' or 'none'.
    line_type = 'solid'

    # Size of marker in pixels
    marker_size = 8

    # Type of marker. Options are 'cross', 'x', 'circle', 'box', or 'none'.
    marker_type ='none'

    # The following option merits an explanation. The y-axis scale used for
    # plotting can be controlled using option 'yscale'. It is a 3-way tuple,
    # with values (ylow, yhigh, min_interval). If set to "None", a parameter is
    # set automatically, otherwise the value is used. However, in the case of
    # min_interval, what is set is the *minimum* y-axis tick interval. 
    yscale = None, None, None

    # For progressive vector plots, you can choose to rotate the vectors.
    # Positive is clockwise.
    # For my area, westerlies overwhelmingly predominate, so by rotating
    # positive 90 degrees, the average vector will point straight up.
    vector_rotate = 90

    # This defines what fraction of the difference between maximum and minimum
    # horizontal chart bounds is considered a gap in the samples and should not
    # be plotted.
    line_gap_fraction = 0.05

    # This controls whether day/night bands will be shown. They only look good
    # on plots wide enough to show individual days such as day and week plots.
    show_daynight = true
    # These control the appearance of the bands if they are shown.
    # Here's a monochrome scheme:
    daynight_day_color   = "#fdfaff"
    daynight_night_color = "#dfdfe2"
    daynight_edge_color  = "#e0d8d8"

    # What follows is a list of subsections, each specifying a time span, such
    # as a day, week, month, or year. There's nothing special about them or
    # their names: it's just a convenient way to group plots with a time span
    # in common. You could add a time span [[biweek_images]] and add the
    # appropriate time length, aggregation strategy, etc., without changing
    # any code.
    #
    # Within each time span, each sub-subsection is the name of a plot to be
    # generated for that time span. The generated plot will be stored using
    # that name, in whatever directory was specified by option 'HTML_ROOT'
    # in weewx.conf.
    #
    # With one final nesting (four brackets!) is the sql type of each line to
    # be included within that plot.
    #
    # Unless overridden, leaf nodes inherit options from their parent

    # Default plot parameters
    plot_type = line
    aggregate_type = none
    width = 1
    time_length = 86400 # 24 hours

    [[day_images]]
        x_label_format = %H:%M
        bottom_label_format = %x %X
        time_length = 97200 # 27 hours

""")
        for dev in config_dict['airQ'].sections:
            image_section(file, config_dict['airQ'][dev], dev, 'day', sensors[dev], obstypes[dev], seasons_lang)

        file.write("""
    [[week_images]]
        x_label_format = %d
        bottom_label_format = %x %X
        time_length = 604800 # 7 days
        aggregate_type = avg
        aggregate_interval = hour

""")
        for dev in config_dict['airQ'].sections:
            image_section(file, config_dict['airQ'][dev], dev, 'week', sensors[dev], obstypes[dev], seasons_lang)

        file.write("""
    [[month_images]]
        x_label_format = %d
        bottom_label_format = %x %X
        time_length = 2592000 # 30 days
        aggregate_type = avg
        aggregate_interval = 10800 # 3 hours
        show_daynight = false

""")
        for dev in config_dict['airQ'].sections:
            image_section(file, config_dict['airQ'][dev], dev, 'month', sensors[dev],obstypes[dev], seasons_lang)

        file.write("""
    [[year_images]]
        x_label_format = %m/%d
        bottom_label_format = %x %X
        time_length = 31536000 # 365 days
        aggregate_type = avg
        aggregate_interval = day
        show_daynight = false

""")
        for dev in config_dict['airQ'].sections:
            image_section(file, config_dict['airQ'][dev], dev, 'year', sensors[dev],obstypes[dev], seasons_lang)

        print("  writing section [Generators]")
        file.write("""###############################################################################

[Generators]
        # The list of generators that are to be run:
        generator_list = weewx.cheetahgenerator.CheetahGenerator, weewx.imagegenerator.ImageGenerator, weewx.reportengine.CopyGenerator

""")
        print("  done.")
    airqlang = SkinLanguage(seasons_skin_path,airq_skin_path,seasons_lang)
    for dev in config_dict['airQ'].sections:
        airqlang.device(config_dict['airQ'][dev].get('prefix'),sensors[dev],obstypes[dev],RoomTypes.get(dev))
    airqlang.close()
    print("creating %s" % os.path.join(airq_skin_path,'index.html.tmpl'))
    with open(os.path.join(airq_skin_path,'index.html.tmpl'),"w") as file:
        file.write(HTML_HEAD)
        file.write('<ul>')
        for dev in config_dict['airQ'].sections:
            file.write('<li><a href="%s.html">%s</a></li>' % (dev,dev))
        file.write("</ul>")
        file.write(HTML_FOOT)
        print("  done.")
    for dev in config_dict['airQ'].sections:
        create_template(config_dict['airQ'][dev],dev,airq_skin_path,sensors[dev],obstypes[dev],gettext_style)

IMG_DICT = [
    ('barometer','pressure',['airqBarometer']),
    ('tempdew','temperature',['airqTemp','airqDewpoint']),
    ('hum','humidity',['airqHumidity']),
    ('humabs','humidity_abs',['airqHumAbs']),
    ('CO2','co2',['co2']),
    ('TVOC','tvoc',['TVOC']),
    ('PM','particulates',['pm1_0','pm2_5','pm10_0']),
    ('CNT','particulates',['cnt0_3','cnt0_5','cnt1_0','cnt2_5','cnt5_0','cnt10_0']),
    ('Idx','co2',['airqPerfIdx','airqHealthIdx']),
    ('noise','sound',['noise']),
    ('CO','co',['airqCO_m']),
    ('NO2','no2',['no2']),
    ('Oxygen','oxygen',['o2']),
    ('Ozone','o3',['airqO3_m']),
    ('Sulfur','so2',['so2','h2s'])]
    
def image_section(file, dev_dict, dev, zeit, sensors, obstypes, lang):
    """ write image section to skin.conf """
    for img in IMG_DICT:
        if img[1] in sensors:
            file.write("""        [[[%s%s%s]]]
""" % (zeit,dev,img[0]))
            for obs in img[2]:
                if obstype_with_prefix(obs,dev_dict.get('prefix')) in obstypes:
                    file.write("""            [[[[%s]]]]
""" % obstype_with_prefix(obs,dev_dict.get('prefix')))
                    if img[1]=='particulates' or obs in ('o3','so2','no2','h2s'):
                        file.write('''                label = "%s"
''' % obs.replace('_',',' if lang and lang=='de' else '.').upper())
        file.write("""
""")

def _gettext_text(page, text, gettext_style):
    if gettext_style not in ('(','['):
        return text
    if page is None:
        cls = ')' if gettext_style=='(' else ']'
        return '$gettext%s%s%s' % (gettext_style,text,cls)
    if gettext_style=='[':
        return '$gettext[%s][%s]' % (page,text)
    return '$pgettext(%s,%s)' % (page,text)

def create_template(dev_dict, dev, airq_skin_path, sensors, obstypes, gettext_style):
    """ create html template """
    fn = dev+'.html.tmpl'
    fn = os.path.join(airq_skin_path,fn)
    print("creating %s" % fn)
    with open(fn,"w") as file:
        file.write(HTML_HEAD % (_gettext_text(None,"'lang'",gettext_style),obstype_with_prefix('airqDeviceID',dev_dict.get('prefix')),obstype_with_prefix('airqStatus',dev_dict.get('prefix'))))
        file.write('''
    <div id="contents">
      <div id="widget_group">
<div id='current_widget' class="widget">
  <div class="widget_title">
    %s
    <a class="widget_control"
      onclick="toggle_widget('current')">&diams;</a>
  </div>

  <div class="widget_contents">
  <table>
    <tbody>
''' % _gettext_text(None,'"Current Conditions"',gettext_style))
        for img in IMG_DICT:
            if img[1] in sensors:
                for obs in img[2]:
                    unit = ''
                    if obs=='airqHumAbs':
                        unit = '.gram_per_meter_cubed'
                    elif obs in ('TVOC','so2','no2'):
                        unit = '.ppb'
                    elif obs=='airqCO_m':
                        unit = '.milligram_per_meter_cubed.format("%.2f")'
                    elif obs=='airqO3_m':
                        unit = '.microgram_per_meter_cubed.format("%.1f")'
                    elif obs in ('pm1_0','pm2_5','pm10_0'):
                        unit = '.format("%.1f")'
                    file.write('''<tr>
            <td class="label">$obs.label.%s</td>
            <td class="data">$current.%s%s</td>
</tr>
''' % (obstype_with_prefix(obs,dev_dict.get('prefix')),obstype_with_prefix(obs,dev_dict.get('prefix')),unit))
        file.write('''    </tbody>
  </table>
  </div>

</div>

      </div>
''')
        file.write('''
      <div id="plot_group">
        <div id="history_widget" class="widget">
          <div id="plot_title" class="widget_title">%s:&nbsp;&nbsp;
''' % _gettext_text(None,'"Plots"',gettext_style))
        file.write('''
            <a class="button_selected" id="button_history_day"
               onclick="choose_history('day')">%s</a>
''' % _gettext_text(None,'"Day"',gettext_style))
        file.write('''
            <a class="button" id="button_history_week"
               onclick="choose_history('week')">%s</a>
''' % _gettext_text(None,'"Week"',gettext_style))
        file.write('''
            <a class="button" id="button_history_month"
               onclick="choose_history('month')">%s</a>
''' % _gettext_text(None,'"Month"',gettext_style))
        file.write('''
            <a class="button" id="button_history_year"
               onclick="choose_history('year')">%s</a>
          </div>
''' % _gettext_text(None,'"Year"',gettext_style))
        for zeit in ('day','week','month','year'):
            file.write('''          <div id="history_%s" class="plot_container">
''' % zeit)
            for img in IMG_DICT:
                if img[1] in sensors:
                    file.write('''            #if $%s.%s.hasdata
            <img src="%s%s%s.png" />
            #end if
''' % (zeit,obstype_with_prefix(img[2][0],dev_dict.get('prefix')),zeit,dev,img[0]))
            file.write('''          </div>
''')
        file.write('''
        </div>
      </div>
''')
        file.write(HTML_FOOT)
        print("  done.")

class SkinLanguage(object):

    def __init__(self, seasons_skin_path, airq_skin_path, lang):
        self.lang = lang
        if lang:
            lang_fn = lang+'.conf'
            self.seasons_lang_path = os.path.join(seasons_skin_path,'lang',lang_fn)
            self.airq_lang_path = os.path.join(airq_skin_path,'lang',lang_fn)
        else:
            print("no language defined")
            self.seasons_lang_path = None
            self.airq_lang_path = None
        if os.path.isfile(self.seasons_lang_path):
            self.seasons_lang = configobj.ConfigObj(self.seasons_lang_path)
        else:
            print("'%s' does not exist" % self.seasons_lang_path)
        if os.path.isfile(self.airq_lang_path):
            ans = y_or_n("'%s' exists. Overwrite? (y/n): " % self.airq_lang_path)
            self.overwrite = ans=='y'
        else:
            self.overwrite = True
        if self.overwrite:
            print("creating %s" % self.airq_lang_path)
            self.airq_lang = configobj.ConfigObj(encoding='utf-8',indent_type='    ')
            self.airq_lang.filename = self.airq_lang_path
            self.airq_lang['Labels'] = {}
            self.airq_lang['Labels']['Generic'] = {}
            self.airq_lang['Texts'] = {}
            for ii in ['Current Conditions','HiLo','Plots','Today','Day','Week','Month','Year','Rainyear','Rainyear1','Rainyear2']:
                    self.airq_lang['Texts'][ii] = self.seasons_lang['Texts'].get(ii,ii)
                    
    def close(self):
        if self.overwrite and self.airq_lang_path:
            self.airq_lang.write()
            print("  done.")
    
    SIMILAR_IN = {
        'airqPressure':'pressure',
        'airqAltimeter':'altimeter',
        'airqBarometer':'barometer',
        'airqTemp':'inTemp',
        'airqHumidity':'inHumidity',
        'airqDewpoint':'inDewpoint',
        'noise':'noise'}
    
    SIMILAR_OUT = {
        'airqPressure':'pressure',
        'airqAltimeter':'altimeter',
        'airqBarometer':'barometer',
        'airqTemp':'outTemp',
        'airqHumidity':'outHumidity',
        'airqDewpoint':'outDewpoint',
        'noise':'noise'}
        
    INDIFFERENT = {
        'airqCO_m':'CO',
        'co':'CO',
        'airqO3_m':'O<sub>3</sub>',
        'o3':'O<sub>3</sub>',
        'so2':'SO<sub>2</sub>',
        'so2_m':'SO<sub>2</sub>',
        'no2':'NO<sub>2</sub>',
        'no2_m':'NO<sub>2</sub>',
        'h2s':'H<sub>2</sub>S',
        'pm1_0':'PM<sub>1.0</sub>',
        'pm2_5':'PM<sub>2.5</sub>',
        'pm10_0':'PM<sub>10.0</sub>',
        'TVOC':'TVOC'}
        
    TRANSLATE = {
        'en':{
            'airqPerfIdx':'Performance index',
            'airqHealthIdx':'Health Index',
            'airqHumAbs':'Absolute humidity',
            'co2':'Carbon dioxide',
            'noise':'Noise',
            'o3':'Ozone',
            'airqO3_m':'Ozone'},
        'de':{
            'airqPerfIdx':'Leistungsindex',
            'airqHealthIdx':'Gesundheitsindex',
            'airqHumAbs':'absolute Luftfeuchte',
            'co2':'Kohlendioxid',
            'noise':'Lärm',
            'o3':'Ozon',
            'airqO3_m':'Ozon'},
        'fr':{
            'airqPerfIdx':'Indice de performance',
            'airqHealthIdx':'Indice de santé',
            'airqHumAbs':'humidité absolue',
            'co2':'Dioxyde de carbone',
            'noise':'Pollution sonore',
            'o3':'Ozone',
            'airqO3_m':'Ozone'}}
    
    def device(self,prefix, sensors, obstypes, RoomType):
        if not self.overwrite or not self.airq_lang_path: return
        if RoomType=='outdoor':
            similar = self.SIMILAR_OUT
        else:
            similar = self.SIMILAR_IN
        for img in IMG_DICT:
            if img[1] in sensors:
                for obs in img[2]:
                    obsp = obstype_with_prefix(obs,prefix)
                    if obs in similar and similar[obs] in self.seasons_lang['Labels']['Generic']:
                        self.airq_lang['Labels']['Generic'][obsp] = self.seasons_lang['Labels']['Generic'].get(similar.get(obs),obsp)
                    elif self.lang in self.TRANSLATE and obs in self.TRANSLATE[self.lang]:
                        self.airq_lang['Labels']['Generic'][obsp] = self.TRANSLATE[self.lang][obs]
                    elif obs in self.INDIFFERENT:
                        self.airq_lang['Labels']['Generic'][obsp] = self.INDIFFERENT[obs]
                    else:
                        self.airq_lang['Labels']['Generic'][obsp] = obsp



if __name__ == "__main__":
    main()

