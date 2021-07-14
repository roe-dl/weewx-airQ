# weewx-airQ
Service for WeeWX to retrieve air quality data from the airQ device of Corant GmbH

PM<sub>1.0</sub>, PM<sub>2.5</sub>, PM<sub>10.0</sub>, TVOC, 
CO, CO<sub>2</sub>, O<sub>2</sub>, O<sub>3</sub>, NO<sub>2</sub>, 
H<sub>2</sub>S, SO<sub>2</sub>, noise, health index, performance index,
temperature, humidity, dewpoint, air pressure

## Installation instructions:

1) download

   wget -O weewx-airQ.zip https://github.com/roe-dl/weewx-airQ/archive/master.zip

2) run the installer

   sudo wee_extension --install weewx-airQ.zip

3) check configuration in weewx.conf

   ```
   [airQ]

       query_interval = 5.0 # this is the default, if option is missing

       [[first_device]]
           host = replace_me_by_host_address_or_IP
           password = replace_me
           #prefix = replace_me # optional
           #altitude = value, unit # optional, default station altitude
           #query_interval = value # optional, if different from general setting

       [[second_device]]
           ...
   ...
   [Engine]
       [[Services]]
           ...
           data_services = ... ,user.airQ-corant.AirqService
   ```
   
5) restart weewx

   ```
   sudo /etc/init.d/weewx stop
   sudo /etc/init.d/weewx start
   ```

## Usage:

Most of the the observation types provided by the airQ device are
predefined within WeeWX. If no special configuration besides host
address and password is provided the measured values are stored to
those observation types. 

More than one device can be used. That is done by configurating a
specific prefix for the observation types of each device.

<img src="dayPM.png" />

## Observation types:

Dependend on hardware configuration the following observation types
are provided. The names are given as if no prefix is specified:

* **airqDeviceID**: (provided if included in `[StdWXCalculate]` only) 
  device ID of the device
* **airqStatus**: (provided if included in `[StdWXCalculate]` only)
  sensor error messages or "OK" if none
* **airqBattery**: battery status (actually not used)
* **co**: CO concentration
* **co2**: CO<sub>2</sub> concentration
* **dCO2dt**: CO<sub>2</sub> changing rate
* **dHdt**: absolute humidity changing rate
* **airqDewpoint**: dewpoint
* **airqDoorEvent**: (experimental) door opened or closed
* **h2s**: H<sub>2</sub>S concentration
* **airqHealthIdx**: health index (special index according to a newly
  developed algorithm from the manufacturer)
* **airqHumidity**: relative humidity
* **airqHumAbs**: absolute humidity
* **airqMeasuretime**: duration of the last measuring cycle
* **no2**: NO<sub>2</sub> concentration
* **o3**: O<sub>3</sub> concentration
* **o2**: O<sub>2</sub> concentration
* **airqPerfIdx**: performance index (special index according to a newly
  developed algorithm from the manufacturer)
* **pm1_0**, **pm2_5**, **pm10_0**: particulate matter 
* **cnt0_3**, **cnt0_5**, **cnt1_0**, **cnt2_5**, **cnt5_0**, **cnt10_0**: 
  amount of particles
  of the appropriate size
* **TypPS**: typical particle size
* **airqPressure**: air pressure
* **airqAltimeter** altimeter value (air pressure corrected by altitude, 
  software calculated, not received from the device)
* **so2**: SO<sub>2</sub> concentration
* **airqNoise**: sound level
* **airqTemp**: temperature
* **TVOC**: volatile organic compounds concentration
* **airqUptime**: uptime of the device

If a prefix is provided "airq" is replaced by the prefix. If the
name does not start by "airq" the prefix is prepended to the name.

## Links:

* [Web site of the airQ device](https://www.air-q.com) 
* [airQ data sheet (german)](https://uploads-ssl.webflow.com/5bd9feee2fb42232fe1d0196/5f898b110a9e9fea8049fa29_air-Q_Specs_de_aktuell_2020-06-25.pdf)
* [WeeWX homepage](http://weewx.com) - [WeeWX Wiki](https://github.com/weewx/weewx/wiki)
* [Wöllsdorf weather conditions](https://www.woellsdorf-wetter.de)
