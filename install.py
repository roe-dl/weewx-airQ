# installer airQ
# Copyright 2021 Johanna Roedenbeck
# Distributed under the terms of the GNU Public License (GPLv3)

from weecfg.extension import ExtensionInstaller

def loader():
    return AirqInstaller()

class AirqInstaller(ExtensionInstaller):
    def __init__(self):
        super(AirqInstaller, self).__init__(
            version="0.9b3",
            name='airQ',
            description='Service to retrieve data from the airQ device of Corant GmbH',
            author="Johanna Roedenbeck",
            author_email="",
            prep_services='user.airQ_corant.AirqUnits',
            data_services='user.airQ_corant.AirqService',
            config={
              'airQ':{
                  'query_interval':'5.0',
                  'volume_mass_method':'1',
                  'first_device':{
                  'host':'replace_me',
                  'password':'replace_me',
                  '#prefix':'replace_me',
                  '#altitude': 'set_if_not_station_altitude'
                  }}},
            files=[('bin/user', ['bin/user/airQ_corant.py','bin/user/airq_conf.py']),
                   ('bin',      ['bin/airq_conf'])]
            )
