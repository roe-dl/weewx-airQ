# weewx-airQ
Service for WeeWX to retrieve data from the airQ device of Corant GmbH

## Installation instructions:

1) download

   wget -O weewx-airQ.zip https://github.com/roe-dl/weewx-airQ/archive/master.zip

2) run the installer

   sudo wee_extension --install weewx-airQ.zip

3) check configuration in weewx.conf

   ```
   [airQ]
       [[first_device]]
           host = replace_me_by_host_address_or_IP
           password = replace_me
           #prefix = replace_me # optional
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

## Observation types:

Dependend on hardware configuration the following observation types
are provided. The names are given as if no prefix is specified:

* airqDeviceID: (provided if included in `[StdWXCalculate]` only) 
  device ID of the device
* airqStatus: (provided if included in `[StdWXCalculate]` only)
  sensor error messages or "OK" if none
* airqBattery: battery status (actually not used)
* co: CO concentration
* co2: CO<sub>2</sub> concentration
* dCO2dt: CO<sub>2</sub> changing rate
* dHdt: absolute humidity changing rate
* airqDewpoint: dewpoint
* airqDoorEvent: (experimental) door opened or closed
* h2s: H<sub>2</sub>S concentration
* airqHealthIdx: health index (special index according to a newly
  developed algorithm from the manufacturer)
* airqHumidity: relative humidity
* airqHumAbs: absolute humidity
* airqMeasuretime: duration of the last measuring cycle
* no2: NO<sub>2</sub> concentration
* o3: O<sub>3</sub> concentration
* o2: O<sub>2</sub> concentration
* airqPerfIdx: performance index (special index according to a newly
  developed algorithm from the manufacturer
* pm1_0, pm2_5, pm10_0: 
* cnt0_3, cnt0_5, cnt1_0, cnt2_5, cnt5_0, cnt10_0: amount of particles
  of the appropriate size
* TypPS: typical particle size
* airqPressure: air pressure
* so2: SO<sub>2</sub> concentration
* airqNoise: sound level
* airqTemp: temperature
* TVOC: volatile organic components concentration
* airqUptime: uptime of the device

If a prefix is provided "airq" is replaced by the prefix. If the
name does not start by "airq" the prefix is prepended to the name.

## Links:

* [Woellsdorf weather](https://www.woellsdorf-wetter.de)
* [Web site of the airQ device](https://www.air-q.com)
