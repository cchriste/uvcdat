############################################################################
##
## Copyright (C) 2006-2007 University of Utah. All rights reserved.
##
## This file is part of VisTrails.
##
## This file may be used under the terms of the GNU General Public
## License version 2.0 as published by the Free Software Foundation
## and appearing in the file LICENSE.GPL included in the packaging of
## this file.  Please review the following to ensure GNU General Public
## Licensing requirements will be met:
## http://www.opensource.org/licenses/gpl-license.php
##
## If you are unsure which license is appropriate for your use (for
## instance, you are interested in developing a commercial derivative
## of VisTrails), please contact us at vistrails@sci.utah.edu.
##
## This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
## WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
##
############################################################################

import os
from core.system import vistrails_root_directory
from db import VistrailsDBException

currentVersion = '0.9.4'

def getVersionDAO(version=None):
    if version is None:
        version = currentVersion
    persistence_dir = 'db.versions.' + get_version_name(version) + \
        '.persistence'
    try:
        persistence = __import__(persistence_dir, {}, {}, [''])
    except ImportError:
        msg = "Cannot find DAO for version '%s'" % version
        raise VistrailsDBException(msg)
    return persistence.DAOList()

def translateVistrail(vistrail, version=None):
    if version is None:
        version = vistrail.version

    version_map = {
        '0.3.0': '0.3.1',
        '0.3.1': '0.6.0',
        '0.5.0': '0.6.0',
        '0.6.0': '0.7.0',
        '0.7.0': '0.8.0',
        '0.8.0': '0.8.1',
        '0.8.1': '0.9.0',
        '0.9.0': '0.9.1',
        '0.9.1': '0.9.3',
        '0.9.2': '0.9.3',
        '0.9.3': '0.9.4',
        }

    def get_translate_module(start_version):
        end_version = version_map[start_version]
        translate_dir = 'db.versions.' + get_version_name(end_version) + \
            '.translate.' + get_version_name(start_version)
        return __import__(translate_dir, {}, {}, [''])

    # don't get stuck in an infinite loop
    count = 0
    while version != currentVersion:
        if count > len(version_map):
            break
        translate_module = get_translate_module(version)
        vistrail = translate_module.translateVistrail(vistrail)
        version = vistrail.db_version
        count += 1

    if version != currentVersion:
        msg = "An error occurred when translating,"
        msg += "only able to translate to version '%s'" % version
        raise VistrailsDBException(msg)

    return vistrail

def get_version_name(version_no):
    return 'v' + version_no.replace('.', '_')

def getVersionSchemaDir(version=None):
    if version is None:
        version = currentVersion
    versionName = get_version_name(version)
    schemaDir = vistrails_root_directory()
    schemaDir = os.path.join(vistrails_root_directory(), 'db', 'versions', 
                             versionName, 'schemas', 'sql')
    return schemaDir
