# installer airQ
# Copyright 2021 Johanna Roedenbeck
# Distributed under the terms of the GNU Public License (GPLv3)

from weecfg.extension import ExtensionInstaller

def loader():
    return AirqInstaller()

class AirqInstaller(ExtensionInstaller):
    def __init__(self):
        super(GTSInstaller, self).__init__(
            version="0.1",
            name='airQ',
            description='Service to retrieve data from the airQ device of Corant GmbH',
            author="Johanna Roedenbeck",
            author_email="",
            data_services='user.airQ-corant.AirqService',
            config={
              'airQ':{
                  'host':'replace_me',
                  'password':'replace_me',
                  '#prefix':'replace_me'
                  }},
            files=[('bin/user', ['bin/user/airQ-corant.py'])]
            )
