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


## Links:

* [Woellsdorf weather](https://www.woellsdorf-wetter.de)
* [Web site of the airQ device](https://www.air-q.com)
