############################################################################
##
## Copyright (C) 2006-2010 University of Utah. All rights reserved.
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
""" This is the application for vistrails when running as a server.

"""
import Queue
import base64
import hashlib
import sys
import logging
import os
import os.path
import subprocess
import tempfile
import time
import urllib
import xmlrpclib

from PyQt4 import QtGui, QtCore
import SocketServer
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from datetime import date, datetime
from time import strptime

from core.configuration import get_vistrails_configuration
from gui.application import VistrailsApplicationInterface
from gui import qt
from core.db.locator import DBLocator, ZIPFileLocator, FileLocator
from core.db import io
import core.db.action

from core.utils import InstanceObject
from core.vistrail.vistrail import Vistrail
from core import command_line
from core import system
from core.modules.module_registry import get_module_registry as module_registry
from core import interpreter
from gui.vistrail_controller import VistrailController
import core
import db.services.io
import gc
import traceback
ElementTree = core.system.get_elementtree_library()

import core.requirements
import core.console_mode

from index import indexworkflow

from db.versions import currentVersion

db_host = 'crowdlabs.sci.utah.edu'
db_read_user = 'vtserver'
db_read_pass = ''
db_write_user = 'repository'
db_write_pass = 'somepass'

################################################################################
class StoppableXMLRPCServer(SimpleXMLRPCServer):
    """This class allows a server to be stopped by a external request"""
    #accessList contains the list of ip addresses and hostnames that can send
    #request to this server. Change this according to your server
    accessList = ['localhost',
                  '127.0.0.1',
                  '127.0.0.2',
                  'vistrails.sci.utah.edu',
                  'vistrails',
                  'crowdlabs',
                  'crowdlabs.sci.utah.edu',
                  '155.98.58.49'
                  ]

    allow_reuse_address = True

    def serve_forever(self):
        self.stop = False
        while not self.stop:
            self.handle_request()

    def verify_request(self, request, client_address):
        print "Receiving request from ", client_address, 
        if client_address[0] in StoppableXMLRPCServer.accessList:
            print " allowed!"
            return 1
        else:
            print " denied!"
            return 0

################################################################################

class ThreadedXMLRPCServer(SocketServer.ThreadingMixIn,
                           StoppableXMLRPCServer): pass
"""This is a multithreaded version of the RPC Server. For each request, the 
    server will spawn a thread. Notice that these threads cannot use any Qt
    related objects because they won't be in the main thread."""
################################################################################

class RequestHandler(object):
    """This class will handle all the requests sent to the server. 
    Add new methods here and they will be exposed through the XML-RPC interface
    """
    def __init__(self, logger, instances):
        self.server_logger = logger
        self.instances = instances
        self.medley_objs = {}
        self.load_medleys()
        self.build_vt_medleys_map()
        self.proxies_queue = None
        self.instantiate_proxies()

    #proxies
    def instantiate_proxies(self):
        """instantiate_proxies() -> None 
        If this server started other instances of VisTrails, this will create 
        the client proxies to connect to them. 
        """
        if len(self.instances) > 0:
            self.proxies_queue = Queue.Queue()
            for uri in self.instances:
                try:
                    proxy = xmlrpclib.ServerProxy(uri)
                    self.proxies_queue.put(proxy)
                    print "Instantiated client for ", uri
                except Exception, e:
                    print "Error when instantiating proxy ",uri
                    print "Exception: ", str(e)
    #utils
    def memory_usage(self):
        """memory_usage() -> dict
        Memory usage of the current process in kilobytes. We plan to 
        use this to clear cache on demand later. 
        I believe this works on Linux only.
        """
        status = None
        result = {'peak': 0, 'rss': 0}
        try:
            # This will only work on systems with a /proc file system
            # (like Linux).
            status = open('/proc/self/status')
            for line in status:
                parts = line.split()
                key = parts[0][2:-1].lower()
                if key in result:
                    result[key] = int(parts[1])
        finally:
            if status is not None:
                status.close()
        return result

    def path_exists_and_not_empty(self, path):
        """path_exists_and_not_empty(path:str) -> boolean
        Returns True if given path exists and it's not empty, otherwise returns
        False.
        """
        if os.path.exists(path):
            n = 0
            for root, dirs, file_names in os.walk(path):
                n += len(file_names)
            if n > 0:
                return True
        return False

    #crowdlabs
    def get_wf_modules(self, host, port, db_name, vt_id, version):
        """get_wf_modules(host:str, port:int, db_name:str, vt_id:int, 
                          version:int) -> list of dict
           Returns a list of information about the modules used in a workflow 
           in a list of dictionaries. The dictionary has the following keys:
           name, package, documentation.
        """
        self.server_logger.info("Request: get_wf_modules(%s,%s,%s,%s,%s)"%(host,
                                                                       port,
                                                                       db_name,
                                                                       vt_id,
                                                                       version))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)

            v = locator.load().vistrail
            p = v.getPipeline(long(version))

            if p:
                result = []
                for module in p.module_list:
                    descriptor = \
                       module_registry().get_descriptor_by_name(module.package,
                                                                module.name,
                                                                module.namespace)
                    if descriptor.module.__doc__:
                        documentation = descriptor.module.__doc__
                    else:
                        documentation = "Documentation not available."
                    result.append({'name':module.name, 
                                              'package':module.package, 
                                              'documentation':documentation})
                return result
            else:
                result = "Error: Pipeline was not materialized"
                self.server_logger.error(result)
        except Exception, e:
            result = "Error: %s"%str(e)
            self.server_logger.error(result)

        return result

    def get_packages(self):
        """get_packages()-> dict
        This returns a dictionary with all the packages available in the 
        VisTrails registry.
        The keys are the package identifier and for each identifier there's a 
        dictionary with modules and description.
        """
        try:
            package_dic = {}

            for package in module_registry().package_list:
                package_dic[package.identifier] = {}
                package_dic[package.identifier]['modules'] = []
                for module in package._db_module_descriptors:
                    if module.module.__doc__:
                        documentation = module.module.__doc__
                    else:
                        documentation = "Documentation not available."
                    package_dic[package.identifier]['modules'].append({'name':module.name, 'package':module.package, 'documentation':documentation})
                package_dic[package.identifier]['description'] = package.description if package.description else "No description available"
            return package_dic
        except Exception, e:
            self.server_logger.error("Error: %s"%str(e))
            return "FAILURE: %s" %str(e)
        
    def add_vt_to_db(self, host, port, db_name, user, vt_filepath, filename, 
                     repository_vt_id, repository_creator):
        """add_vt_to_db(host:str, port:int, db_name:str, user:str, 
                        vt_filepath:str, filename:str, repository_vt_id:int, 
                        repository_creator:str) -> int 
        This will add a vistrail in vt_filepath to the the database. Before
        adding it it will annotate the vistrail with the repository_vt_id and 
        repository_creator.
                        
        """                
        try:
            locator = ZIPFileLocator(vt_filepath).load()
            # set some crowdlabs id info
            if repository_vt_id != -1:
                vistrail = locator.vistrail
                vistrail.set_annotation('repository_vt_id', repository_vt_id)
                vistrail.set_annotation('repository_creator', repository_creator)
            #print "name=%s"%filename
            db_locator = DBLocator(host=host, port=int(port), database=db_name,
                                   name=filename, user=db_write_user, passwd=db_write_pass)
            db_locator.save_as(locator)
            #print "db_locator obj_id %s" % db_locator.obj_id
            return db_locator.obj_id
        except Exception, e:
            import traceback
            traceback.print_exc()
            self.server_logger.error("Error: %s"%str(e))
            return "FAILURE: %s" %str(e)

    def merge_vt(self, host, port, db_name, user, new_vt_filepath,
                 old_db_vt_id):
        # XXX: It should be complete now, but I haven't tested it (--Manu).
        try:
            new_locator = ZIPFileLocator(new_vt_filepath)
            new_bundle = new_locator.load()
            new_locator.save(new_bundle)
            old_db_locator = DBLocator(host=host, port=int(port), database=db_name,
                                       obj_id=old_db_vt_id, user=db_write_user, passwd=db_write_pass)
            old_db_bundle = old_db_locator.load()
            db.services.vistrail.merge(old_db_bundle, new_bundle, 'vistrails')
            old_db_locator.save(old_db_bundle)
            new_locator.save(old_db_bundle)
            return 1
        except Exception, e:
            self.server_logger.error("Error: %s"%str(e))
            import traceback
            traceback.print_exc()
            return "FAILURE: %s" %str(e)
        
    def remove_vt_from_db(self, host, port, db_name, user, vt_id):
        """remove_vt_from_db(host:str, port:int, db_name:str, user:str,
                             vt_id:int) -> 0 or 1
        Remove a vistrail from the repository
        """
        config = {}
        config['host'] = host
        config['port'] = int(port)
        config['db'] = db_name
        config['user'] = db_write_user
        config['passwd'] = db_write_pass
        try:
            conn = db.services.io.open_db_connection(config)
            db.services.io.delete_entity_from_db(conn,'vistrail', vt_id)
            db.services.io.close_db_connection(conn)
            return 1
        except Exception, e:
            self.server_logger.error("Error: %s"%str(e))
            if conn:
                db.services.io.close_db_connection(conn)
            return "FAILURE: %s" %str(e)

    def get_runnable_workflows(self, host, port, db_name, vt_id):
        print "get_runnable_workflows"
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)
            (vistrail, _, _)  = io.load_vistrail(locator)

            # get server packages
            local_packages = [x.identifier for x in \
                              module_registry().package_list]

            runnable_workflows = []
            py_source_workflows = []
            local_data_modules = ['File', 'FileSink', 'Path']

            # find runnable workflows
            for version_id, version_tag in vistrail.get_tagMap().iteritems():
                pipeline = vistrail.getPipeline(version_id)
                workflow_packages = set()
                on_repo = True
                has_python_source = False
                for module in pipeline.module_list:
                    # count modules that use data unavailable to web repo
                    if module.name[-6:] == 'Reader' or \
                       module.name in local_data_modules:
                        has_accessible_data = False
                        for edge in pipeline.graph.edges_to(module.id):
                            # TODO check for RepoSync checksum param
                            if pipeline.modules[edge[0]].name in \
                               ['HTTPFile', 'RepoSync']:
                                has_accessible_data = True

                        if not has_accessible_data:
                            on_repo = False

                    elif module.name == "PythonSource":
                        has_python_source = True

                    # get packages used in tagged versions of this VisTrail
                    workflow_packages.add(module.package)

                # ensure workflow doesn't use unsupported packages
                if not filter(lambda p: p not in local_packages,
                              workflow_packages):
                    if has_python_source and on_repo and \
                       version_id not in py_source_workflows:
                        py_source_workflows.append(version_id)

                    elif not has_python_source and on_repo and \
                            version_id not in runnable_workflows:
                        runnable_workflows.append(version_id)

            self.server_logger.info("SUCCESS!")
            print "\n\nRunnable Workflows Return"
            for wf_id in runnable_workflows:
                print vistrail.get_tag(wf_id)
            print "\n\nPython Source Workflows Return"
            for wf_id in py_source_workflows:
                print vistrail.get_tag(wf_id)
            print "\n\n"
            return runnable_workflows, py_source_workflows

        except Exception, e:
            self.server_logger.error("Error: %s"%str(e))
            return "FAILURE: %s" %str(e)

    #medleys
    def build_vt_medleys_map(self):
        self.medleys_map = {}
        self.medleys = {}
        for (m_id,m) in self.medley_objs.iteritems():
            medley = {}
            medley['id'] = m_id
            medley['name'] = m._name
            self.medleys[str(m_id)] = m._name
            if self.medleys_map.has_key((m._vtid,m._version)):
                self.medleys_map[(m._vtid,m._version)].append(medley)
            else:
                self.medleys_map[(m._vtid,m._version)] = [medley]
        print self.medleys
        print self.medleys_map.keys()
        
        
    def load_medleys(self):
        #we will hard code for now 
        #medley "Climatology"
        alias_list = {}
        component = ComponentSimpleGUI(39,1,"Parameter","bool", val="True",
                                       widget="checkbox")
        alias = AliasSimpleGUI(39, "yearly", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(40,2,"Parameter","bool", val="False",
                                       widget="checkbox")
        alias = AliasSimpleGUI(40, "show_surface", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(41,3,"Parameter","bool", val="False",
                                       widget="checkbox")
        alias = AliasSimpleGUI(41, "show_anomaly", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(42,4,"Parameter","int", val="14",
                                       strvalueList="14,16",
                                       widget="combobox")
        alias = AliasSimpleGUI(42, "db",component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(43,5,"Parameter","int", val="8", minVal="1",
                                       maxVal="12", stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(43, "month",component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(44,6,"Parameter","int", val="1999",
                                       minVal="1999", maxVal="2007",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(44, "from_year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(45,7,"Parameter","int", val="2007",
                                       minVal="1999", maxVal="2009", 
                                       stepSize="1", widget="numericstepper")
        alias = AliasSimpleGUI(45, "to_year", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(6, "Climatology", 16, 91, alias_list, 'vistrail')
        self.medley_objs[6] = medley

        #medley "Stars"
        alias_list = {}

        component = ComponentSimpleGUI(51,1,"Parameter","float", val="-0.041", 
                                       strvalueList="-0.06,-0.041,-0.02,0.00,0.02",
                                       widget="combobox")
        alias = AliasSimpleGUI(51, "omega_frame", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(52,2,"Parameter","float", val="0.001")
        alias = AliasSimpleGUI(52, "rho_min", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(53,3,"Parameter","float", val="3.2",
                                       minVal="1", maxVal="10", stepSize="0.1")
        alias = AliasSimpleGUI(53, "propagation_time", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(8, "Stars", 15, 1,
                                 alias_list, 'vistrail')
        self.medley_objs[8] = medley

        #medley "Estuary"
        alias_list = {}

        component = ComponentSimpleGUI(59,1,"Parameter","int", val="11",
                                       minVal="11", maxVal="11",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(59, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(60,2,"Parameter","int", val="7",
                                       minVal="6", maxVal="7",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(60, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(61,3,"Parameter","int", val="2009",
                                       minVal="2009", maxVal="2009",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(61, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(62,4,"Parameter","float", val="1",
                                       strvalueList="1,5,10,20",
                                       widget="combobox")
        alias = AliasSimpleGUI(62, "Plane Depth", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(63,5,"Parameter","float", val="1",
                                       minVal="1", maxVal="3", stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(63, "Run Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(64,6,"Parameter","int", val="20",
                                       minVal="1", maxVal="71", stepSize="10",
                                       widget="slider", seq=True)
        alias = AliasSimpleGUI(64, "Run Timestep", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(65,7,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Run Scalars", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(9, "Estuary", 19, 47,
                                 alias_list, 'vistrail')
        self.medley_objs[9] = medley

        #medley "Plume"
        alias_list = {}

        component = ComponentSimpleGUI(59,1,"Parameter","int", val="11",
                                       minVal="11", maxVal="11",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(59, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(60,2,"Parameter","int", val="7",
                                       minVal="6", maxVal="7",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(60, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(61,3,"Parameter","int", val="2009",
                                       minVal="2009", maxVal="2009",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(61, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(62,4,"Parameter","float", val="1",
                                       strvalueList="1,5,10,20",
                                       widget="combobox")
        alias = AliasSimpleGUI(62, "Plane Depth", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(63,5,"Parameter","float", val="1",
                                       minVal="1", maxVal="3", stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(63, "Run Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(64,6,"Parameter","int", val="20",
                                       minVal="1", maxVal="71", stepSize="10",
                                       widget="slider", seq=True)
        alias = AliasSimpleGUI(64, "Run Timestep", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(65,7,"Parameter","string", val="salt",
                                       strvalueList="salt,temp", 
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Run Scalars", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(10, "Plume", 19, 78,
                                 alias_list, 'vistrail')
        self.medley_objs[10] = medley

        #medley "Mouth"
        # alias_list = {}

        # component = ComponentSimpleGUI(64,1,"Parameter","float", val="3",
        #                                strvalueList="1,3,7,12",
        #                                widget="combobox")
        # alias = AliasSimpleGUI(64, "Plane Depth", component=component)
        # alias_list[alias._name] = alias

        # component = ComponentSimpleGUI(65,2,"Parameter","string",
        #                    val="/home/workspace/ccalmr/hindcasts/2004-12-16/run/",
        #                    widget="text")
        # alias = AliasSimpleGUI(65, "Run Directory", component=component)
        # alias_list[alias._name] = alias

        # component = ComponentSimpleGUI(66,3,"Parameter","float", val="7",
        #                                minVal="1", maxVal="7", stepSize="1",
        #                                widget="numericstepper")
        # alias = AliasSimpleGUI(66, "Run Day", component=component)
        # alias_list[alias._name] = alias

        # component = ComponentSimpleGUI(67,4,"Parameter","int", val="20",
        #                                minVal="1", maxVal="90", stepSize="5",
        #                                widget="slider", seq=True)
        # alias = AliasSimpleGUI(67, "Run Timestep", component=component)
        # alias_list[alias._name] = alias

        # component = ComponentSimpleGUI(68,5,"Parameter","string", val="salt",
        #                                strvalueList="salt,temp", 
        #                                widget="combobox")
        # alias = AliasSimpleGUI(68, "Run Scalars", component=component)
        # alias_list[alias._name] = alias

        # medley = MedleySimpleGUI(11, "Mouth", 13, 486,
        #                          alias_list, 'vistrail')
        # self.medley_objs[11] = medley

        #medley effn7 timeseries
        alias_list = {}

        component = ComponentSimpleGUI(69,1,"Parameter","int", val="11",
                                       minVal="11", maxVal="11",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(69, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(70,2,"Parameter","int", val="6",
                                       minVal="6", maxVal="7",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(70, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(71,3,"Parameter","int", val="2009",
                                       minVal="2009", maxVal="2009",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(71, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(72,4,"Parameter","string", val="salt",
                                       strvalueList="salt,temp", 
                                       widget="combobox")
        alias = AliasSimpleGUI(72, "variable", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(12, "effn7 timeseries", 13, 622,
                                 alias_list, 'vistrail')
        self.medley_objs[12] = medley

        #medley elevation
        alias_list = {}

        component = ComponentSimpleGUI(69,1,"Parameter","int", val="11",
                                       minVal="11", maxVal="11",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(69, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(70,2,"Parameter","int", val="6",
                                       minVal="6", maxVal="7",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(70, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(71,3,"Parameter","int", val="2009",
                                       minVal="2009", maxVal="2009",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(71, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(72,4,"Parameter","string", val="effn7",
                                       strvalueList="am169,effn1,effn2,effn3,effn4,effn5,effn6,effn7", 
                                       widget="combobox")
        alias = AliasSimpleGUI(72, "station", component=component)
        alias_list[alias._name] = alias


        medley = MedleySimpleGUI(13, "elevation", 18, 5,
                                 alias_list, 'vistrail')
        self.medley_objs[13] = medley

        #medley effn1 timeseries
        alias_list = {}

        component = ComponentSimpleGUI(69,1,"Parameter","int", val="11",
                                       minVal="11", maxVal="11",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(69, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(70,2,"Parameter","int", val="6",
                                       minVal="6", maxVal="7",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(70, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(71,3,"Parameter","int", val="2009",
                                       minVal="2009", maxVal="2009",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(71, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(72,4,"Parameter","string", val="salt",
                                       strvalueList="salt,temp", 
                                       widget="combobox")
        alias = AliasSimpleGUI(72, "variable", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(14, "effn1 timeseries", 18, 15,
                                 alias_list, 'vistrail')
        self.medley_objs[14] = medley

        #medley effn2 timeseries
        alias_list = {}

        component = ComponentSimpleGUI(69,1,"Parameter","int", val="11",
                                       minVal="11", maxVal="11",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(69, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(70,2,"Parameter","int", val="6",
                                       minVal="6", maxVal="7",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(70, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(71,3,"Parameter","int", val="2009",
                                       minVal="2009", maxVal="2009",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(71, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(72,4,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(72, "variable", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(15, "effn2 timeseries", 18, 16,
                                 alias_list, 'vistrail')
        self.medley_objs[15] = medley

        #medley am169 timeseries
        alias_list = {}

        component = ComponentSimpleGUI(69,1,"Parameter","int", val="11",
                                       minVal="11", maxVal="11",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(69, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(70,2,"Parameter","int", val="6",
                                       minVal="6", maxVal="7",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(70, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(71,3,"Parameter","int", val="2009",
                                       minVal="2009", maxVal="2009",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(71, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(72,4,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(72, "variable", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(16, "am169 timeseries", 18, 17,
                                 alias_list, 'vistrail')
        self.medley_objs[16] = medley
        
        #medley "Estuary"
        alias_list = {}

        component = ComponentSimpleGUI(59,1,"Parameter","int", val="3",
                                       minVal="3", maxVal="3",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(59, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(60,2,"Parameter","int", val="4",
                                       minVal="4", maxVal="10",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(60, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(61,3,"Parameter","int", val="2008",
                                       minVal="2008", maxVal="2008",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(61, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(62,4,"Parameter","int", val="1",
                                       minVal="0", maxVal="23", stepSize="1",
                                       widget="slider", seq=True)
        alias = AliasSimpleGUI(62, "Time (in hours)", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(65,7,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Run Scalars", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(17, "Surface Estuary by Date (DB16)", 23, 331,
                                 alias_list, 'vistrail')
        self.medley_objs[17] = medley

        #medley "Estuary 2"
        alias_list = {}

        component = ComponentSimpleGUI(59,1,"Parameter","int", val="3",
                                       minVal="3", maxVal="3",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(59, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(60,2,"Parameter","int", val="4",
                                       minVal="4", maxVal="10",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(60, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(61,3,"Parameter","int", val="2008",
                                       minVal="2008", maxVal="2008",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(61, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(62,4,"Parameter","int", val="1",
                                       minVal="0", maxVal="23", stepSize="1",
                                       widget="slider", seq=True)
        alias = AliasSimpleGUI(62, "Time (in hours)", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(65,7,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Run Scalars", component=component)
        alias_list[alias._name] = alias

        medley = MedleySimpleGUI(18, "New Surface Estuary by Date (DB16)", 24, 14,
                                 alias_list, 'vistrail')
        self.medley_objs[18] = medley
        
        #medley Estuary DB16
        alias_list = {}

        component = ComponentSimpleGUI(59,1,"Parameter","int", val="3",
                                       minVal="3", maxVal="3",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(59, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(60,2,"Parameter","int", val="4",
                                       minVal="4", maxVal="10",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(60, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(61,3,"Parameter","int", val="2008",
                                       minVal="2008", maxVal="2008",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(61, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(62,6,"Parameter","int", val="1",
                                       minVal="0", maxVal="23", stepSize="1",
                                       widget="slider", seq=True)
        alias = AliasSimpleGUI(62, "Time (in hours)", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(65,4,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Run Scalars", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(66,5,"Parameter","string", val="Surface",
                                       strvalueList="Bottom,Surface",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Depth", component=component)
        alias_list[alias._name] = alias
        
        medley = MedleySimpleGUI(19, "Estuary by Date (DB16)", 26, 19,
                                 alias_list, 'vistrail')
        self.medley_objs[19] = medley
        
        #medley Estuary DB14
        alias_list = {}

        component = ComponentSimpleGUI(59,1,"Parameter","int", val="3",
                                       minVal="3", maxVal="3",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(59, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(60,2,"Parameter","int", val="4",
                                       minVal="4", maxVal="10",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(60, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(61,3,"Parameter","int", val="2008",
                                       minVal="2008", maxVal="2008",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(61, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(62,6,"Parameter","int", val="1",
                                       minVal="0", maxVal="23", stepSize="1",
                                       widget="slider", seq=True)
        alias = AliasSimpleGUI(62, "Time (in hours)", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(65,4,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Run Scalars", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(66,5,"Parameter","string", val="Surface",
                                       strvalueList="Bottom,Surface",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Depth", component=component)
        alias_list[alias._name] = alias
        
        medley = MedleySimpleGUI(20, "Estuary by Date (DB14)", 26, 27,
                                 alias_list, 'vistrail')
        self.medley_objs[20] = medley
        
        #medley Estuary f22
        alias_list = {}

        component = ComponentSimpleGUI(59,1,"Parameter","int", val="3",
                                       minVal="3", maxVal="3",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(59, "Month", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(60,2,"Parameter","int", val="3",
                                       minVal="3", maxVal="3",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(60, "Day", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(61,3,"Parameter","int", val="2010",
                                       minVal="2010", maxVal="2010",stepSize="1",
                                       widget="numericstepper")
        alias = AliasSimpleGUI(61, "Year", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(62,7,"Parameter","int", val="1",
                                       minVal="0", maxVal="23", stepSize="1",
                                       widget="slider", seq=True)
        alias = AliasSimpleGUI(62, "Time (in hours)", component=component)
        
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(65,4,"Parameter","string", val="salt",
                                       strvalueList="salt,temp",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Run Scalars", component=component)
        alias_list[alias._name] = alias

        component = ComponentSimpleGUI(66,5,"Parameter","string", val="Surface",
                                       strvalueList="Bottom,Surface",
                                       widget="combobox")
        alias = AliasSimpleGUI(65, "Depth", component=component)
        alias_list[alias._name] = alias
        
        component = ComponentSimpleGUI(67,6,"Parameter","string", val="1",
                                       minVal="", maxVal="", stepSize="",
                                       strvalueList="1,2,3",
                                       widget="combobox")
        alias = AliasSimpleGUI(67, "Run Day", component=component)
        alias_list[alias._name] = alias
        
        medley = MedleySimpleGUI(21, "Estuary by Date (f22)", 26, 106,
                                 alias_list, 'vistrail')
        self.medley_objs[21] = medley
        
        print "medleys loaded..."
                
    def getMedleys(self):
        self.server_logger.info("getMedleys request received")
        res = []
        for k,v in self.medley_objs.iteritems():
            medley = {}
            medley['id'] = k
            medley['name'] = v._name
            res.append(medley)

        self.server_logger.info("returning %s"%res)
        return res

    def getMedleysXML(self):
        self.server_logger.info("getMedleysXML request received")
        print "getMedleysXML request received"
        res = '<medleys>'
        for k,v in self.medley_objs.iteritems():
            res += '<medley id="%s" name="%s" />'% (k,v._name)
        res += '</medleys>'
        self.server_logger.info("returning %s"%res)
        print "returning %s"%res
        return res
    
    def getMedleyById(self, m_id):
        self.server_logger.info( "getMedleyById(%s) request received"%m_id)
        print "getMedleyById(%s) request received"%m_id
        try:
            m_id = int(m_id)
        except Exception, e:
            print "getmedley ", str(e)
            return None
        try:
            root = self.medley_objs[m_id].to_xml()
        except Exception, e:
            print str(e)
        msg = ElementTree.tostring(root)
        print "returning: ", msg
        self.server_logger.info( "returning %s"%msg)
        return msg
    
    def get_vt_from_medley(self, m_id):
        self.server_logger.info( "get_vt_from_medley(%s) request received"%m_id)
        print "get_vt_from_medley(%s) request received"%m_id
        result = []
        try:
            m_id = int(m_id)
        except Exception, e:
            print "getmedley ", str(e)
            return None
        try:
            medley = self.medley_objs[m_id]
            result = '<medley vtid="%s" version="%s" />'% (medley._vtid,
                                                           medley._version)
        except Exception, e:
            print str(e)
        print "returning: ", result
        self.server_logger.info( "returning %s"%result)
        return result
    
    def executeMedley(self, xml_medley, extra_info=None):
        #print xml_medley
        self.server_logger.info("executeMedley request received")
        print "executeMedley request received ", xml_medley
        print "extra_info: ", extra_info
        try:
            self.server_logger.info(xml_medley)
            xml_string = xml_medley.replace('\\"','"')
            root = ElementTree.fromstring(xml_string)
            print 2
            try:
                medley = MedleySimpleGUI.from_xml(root)
            except:
                traceback.print_exc()
            print "%s medley: %s"%(medley._type, medley._name)
            result = ""
            subdir = hashlib.sha224(xml_string).hexdigest()
            self.server_logger.info(subdir)
            path_to_images = \
               os.path.join('/server/crowdlabs/site_media/media/medleys/images',
                            subdir)
            if (not self.path_exists_and_not_empty(path_to_images) and 
                self.proxies_queue is not None):
                #this server can send requests to other instances
                proxy = self.proxies_queue.get()
                try:
                    print "Sending request to ", proxy
                    if extra_info is not None:
                        result = proxy.executeMedley(xml_medley, extra_info)
                    else:
                        result = proxy.executeMedley(xml_medley)
                    self.proxies_queue.put(proxy)
                    print "returning %s"% result
                    self.server_logger.info("returning %s"% result)
                    return result
                except Exception, e:
                    print "Exception: ", str(e)
                    return ""
                
            if extra_info is None:
                extra_info = {}
            
            if extra_info.has_key('pathDumpCells'):
                if extra_info['pathDumpCells']:
                    extra_path = extra_info['pathDumpCells']
            else:        
                extra_info['pathDumpCells'] = path_to_images
               
            #self.server_logger.info(self.temp_configuration.spreadsheetDumpCells)
            #print self.path_exists_and_not_empty(
            #    self.temp_configuration.spreadsheetDumpCells)
            if not self.path_exists_and_not_empty(extra_info['pathDumpCells']):
                if not os.path.exists(extra_info['pathDumpCells']):
                    os.mkdir(extra_info['pathDumpCells'])
                #print self.temp_configuration.spreadsheetDumpCells
                self.server_logger.info(xml_string)
                if medley._type == 'vistrail':
                    print "medley", medley._vtid
                    locator = DBLocator(host=db_host,
                                        port=3306,
                                        database='vistrails',
                                        user='vtserver',
                                        passwd='',
                                        obj_id=medley._vtid,
                                        obj_type=None,
                                        connection_id=None)

                    workflow = medley._version
                    print workflow
                    sequence = False
                    for (k,v) in medley._alias_list.iteritems():
                        if v._component._seq == True:
                            sequence = True
                            val = XMLObject.convert_from_str(v._component._minVal,
                                                             v._component._spec)
                            maxval = XMLObject.convert_from_str(v._component._maxVal,
                                                             v._component._spec)
                            #making sure the filenames are generated in order
                            mask = '%s'
                            if type(maxval) in [type(1), type(1L)]:
                                mask = '%0' + str(len(v._component._maxVal)) + 'd'
                            
                            while val <= maxval:
                                s_alias = "%s=%s$&$" % (k,val)
                                for (k2,v2) in medley._alias_list.iteritems():
                                    if k2 != k and v2._component._val != '':
                                        s_alias += "%s=%s$&$" % (k2,v2._component._val)
                                #print locator
                                #print "\n\n\n >>>>> ", s_alias
                                if s_alias != '':
                                    s_alias = s_alias[:-3]
                                    print "Aliases: ", s_alias
                                try:
                                    gc.collect()
                                    results = \
                                      core.console_mode.run_and_get_results( \
                                                    [(locator,int(workflow))],
                                                    s_alias, 
                                                    extra_info=extra_info)
                                    print self.memory_usage()
                                    interpreter.cached.CachedInterpreter.flush()
                                except Exception, e:
                                    print "Exception: ", str(e)

                                ok = True
                                for r in results:
                                    (objs, errors, _) = (r.objects, r.errors, r.executed)
                                    for e in errors.itervalues():
                                        print "Error: ", str(e)
                                    for i in objs.iterkeys():
                                        if errors.has_key(long(i)):
                                            ok = False
                                            result += str(errors[i])
                                if ok:
                                    print "renaming files ... "
                                    for root, dirs, file_names in os.walk(extra_info['pathDumpCells']):
                                        break
                                    n = len(file_names)
                                    s = []
                                    for f in file_names:
                                        if f.lower().endswith(".png"):
                                            fmask = "%s_"+mask+"%s"
                                            os.renames(os.path.join(root,f), 
                                                       os.path.join(root,"%s" % f[:-4],
                                                                    fmask% (f[:-4],val,f[-4:])))
                                if val < maxval:
                                    val += XMLObject.convert_from_str(v._component._stepSize,
                                                                      v._component._spec)
                                    if val > maxval:
                                        val = maxval
                                else:
                                    break

                    if not sequence:
                        s_alias = ''
                        for (k,v) in medley._alias_list.iteritems():
                            if v._component._val != '':
                                s_alias += "%s=%s$&$" % (k,v._component._val)
                        #print locator
                        #print s_alias
                        if s_alias != '':
                            s_alias = s_alias[:-3]
                            print "Aliases: ", s_alias
                        try:
                            results = \
                               core.console_mode.run_and_get_results( \
                                                [(locator,int(workflow))],
                                                    s_alias,
                                                    extra_info=extra_info)
                        except Exception, e:
                            print "Exception: ", str(e)

                        ok = True
                        for r in results:
                            (objs, errors, _) = (r.objects, r.errors, r.executed)
                            for e in errors.itervalues():
                                print "Error:", str(e)
                            for i in objs.iterkeys():
                                if errors.has_key(long(i)):
                                    ok = False
                                    result += str(errors[i])

                    self.server_logger.info( "success?  %s"% ok)

                elif medley._type == 'visit':
                    cur_dir = os.getcwd()
                    os.chdir(self.temp_configuration.spreadsheetDumpCells)
                    if medley._id == 6:
                        session_file = 'crotamine.session'
                    elif medley._id == 7:
                        session_file = '1NTS.session'
                    else:
                        session_file = 'head.session'
                    session_file = '/server/code/visit/saved_sessions/' + session_file
                    self.server_logger.info("session_file: %s"%session_file)
                    ok = os.system('/server/code/visit/vistrails_plugin/visit/render-session.sh ' + session_file) == 0
                    self.server_logger.info( "success?  %s"% ok)
                    os.chdir(cur_dir)
            else:
                self.server_logger.info("Found cached images.")
                ok = True

            if ok:
                s = []
                print "images path: ", extra_info['pathDumpCells']
                for root, dirs, file_names in os.walk(extra_info['pathDumpCells']):
                    sub = []
                    #n = len(file_names)
                    #print "%s file(s) generated" % n
                    file_names.sort()
                    for f in file_names:
                        sub.append(os.path.join(root[root.find(subdir):],
                                              f))
                    s.append(";".join(sub))
                result = ":::".join(s)
                #FIXME: copy images to extra_path
            print result
            self.server_logger.info("returning %s"% result)
            return result
        except Exception, e:
            self.server_logger.info("Exception: " + str(e))
            print "Exception: " + str(e)

    def getMedleysUsingWorkflow(self, vt_id, workflow):
        print "getMedleyMedleysUsingWorkflow(%s,%s) request received"%(vt_id,
                                                                     workflow)
        self.server_logger.info( \
            "getMedleyMedleysUsingWorkflow(%s,%s) request received"%(vt_id,
                                                                     workflow))
        try:
            vt_id = int(vt_id)
            workflow = int(workflow)
        except Exception, e:
            print "Error ", str(e)
            return []
        try:
            res = self.medleys_map[(vt_id,workflow)]
        except KeyError, e:
            res = []

        self.server_logger.info( "returning %s"%res)

        return res

    def getMedleysUsingVistrail(self, vt_id):
        self.server_logger.info( \
            "getMedleyMedleysUsingVistrail(%s) request received"%vt_id)
        try:
            vt_id = int(vt_id)
        except Exception, e:
            print "Error ", str(e)
            return []
        res = []
        for (key,m_list) in self.medleys_map.iteritems():
            if key[0] == vt_id:
                res.extend(m_list)

        self.server_logger.info( "returning %s"%res)

        return res

    def add_medley_to_db(self, host, port, db_name, medley_name, medley_xmlstr, vt_id,
                         wf_id):
        config = {
                  'host': str(host),
                  'port': int(port),
                  'user': db_write_user,
                  'passwd': db_write_pass,
                  'db': str(db_name)
                  }
        conn = db.services.io.open_db_connection(config)
        command = """INSERT INTO medley (name, xml, vt_id, wf_id)
        VALUES (%s, %s, %s, %s) 
        """
        result = -1
        try:
            c = conn.cursor()
            c.execute(command % (medley_name, medley_xmlstr,vt_id, wf_id)) 
            rows = c.fetchall()
            result = rows
            c.close()
            close_db_connection(db)
        
        except Exception, e:
            msg = "Couldn't add medley to the database: %s"% str(e)
        
        return result
    
    #vistrails
    def run_from_db(self, host, port, db_name, vt_id, path_to_figures,
                    version=None,  pdf=False, vt_tag='',parameters=''):
#        self.server_logger.info("Request: run_vistrail_from_db(%s,%s,%s,%s,%s,%s,%s,%s)"%\
        print "Request: run_from_db(%s,%s,%s,%s,%s,%s,%s,%s,%s)"%\
                                                                    (host,
                                                             port,
                                                             db_name,
                                                             vt_id,
                                                             path_to_figures,
                                                             version,
                                                             pdf,
                                                             vt_tag,
                                                             parameters)
        print self.path_exists_and_not_empty(path_to_figures)
        print self.proxies_queue
        if (not self.path_exists_and_not_empty(path_to_figures) and
            self.proxies_queue is not None):
            print "Will forward request "
            #this server can send requests to other instances
            proxy = self.proxies_queue.get()
            try:
                print "Sending request to ", proxy
                result = proxy.run_from_db(host, port, db_name, vt_id, 
                                           path_to_figures, version, pdf, vt_tag,
                                           parameters)
                self.proxies_queue.put(proxy)
                print "returning %s"% result
                self.server_logger.info("returning %s"% result)
                return result
            except Exception, e:
                print "Exception: ", str(e)
                return ""
            
        extra_info = {}
        extra_info['pathDumpCells'] = path_to_figures
        extra_info['pdf'] = pdf
        # execute workflow
        ok = True
        print "will execute here"
        if not self.path_exists_and_not_empty(extra_info ['pathDumpCells']):
            if not os.path.exists(extra_info ['pathDumpCells']):
                os.mkdir(extra_info ['pathDumpCells'])
            result = ''
            if vt_tag !='':
                version = vt_tag;
            try:
                locator = DBLocator(host=host,
                                    port=int(port),
                                    database=db_name,
                                    user=db_write_user,
                                    passwd=db_write_pass,
                                    obj_id=int(vt_id),
                                    obj_type=None,
                                    connection_id=None)
                print "created locator"
                results = []
                try:
                    results = \
                    core.console_mode.run_and_get_results([(locator,
                                                          int(version))],
                                                          parameters,
                                                          extra_info=extra_info)
                    print "results: %s" % results

                except Exception, e:
                    print str(e)
                ok = True
                for r in results:
                    print r
                    (objs, errors, _) = (r.objects, r.errors, r.executed)
                    for i in objs.iterkeys():
                        if errors.has_key(i):
                            ok = False
                            result += str(errors[i])
            except Exception, e:
                self.server_logger.info("Failure: %s"% str(e))
                return "FAILURE: %s"% str(e)

        if ok:
            self.server_logger.info("Success")
            return "SUCCESS"
        else:
            self.server_logger.info("Failure: %s"%result)
            return "FAILURE: " + result
        
    def get_package_list(self):
        """ get_package_list() -> str
         Returns a list of supported packages identifiers delimited by || """
        try:
            packages = [x.identifier for x in module_registry().package_list]
            return '||'.join(packages)
        except Exception, e:
            print "Exception :", str(e)
            return ''
        
    def get_wf_datasets(self, host, port, db_name, vt_id, version):
        print 'get workflow datasets'
        self.server_logger.info("Request: get_wf_datasets(%s,%s,%s,%s,%s)"%(host,
                                                                           port,
                                                                           db_name,
                                                                           vt_id,
                                                                           version))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)

            v = locator.load().vistrail
            p = v.getPipeline(long(version))

            if p:
                result = []
                for module in p.module_list:
                    if module.name == "RepoSync":
                        for function in module.functions:
                            if function.name == 'checksum':
                                result.append(function.parameters[0].value())
                return result
            else:
                result = "Error: Pipeline was not materialized"
                self.server_logger.info(result)
        except Exception, e:
            result = "Error: %s"%str(e)
            self.server_logger.info(result)
        return result

    def remove_workflow_index(self, wf_id):
        print 'remove a workflow from the index'
        self.server_logger.info("Request: remove_workflow_index(%s)" % (wf_id))
        try:
            wi = indexworkflow.WorkflowIndexer()
            wi.remove(wf_id)
            wi.close()
        except Exception, e:
            result = "Error: %s"%str(e)
            self.server_logger.info(result)
        return 0

    def index_workflow(self, host, port, db_name, vt_id, wf_info):
        print 'index the workflows in a vistrail'
        self.server_logger.info("Request: index_workflow(%s,%s,%s,%s,%s)" % \
                                    (host, port, db_name, vt_id, wf_info))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)

            v = locator.load().vistrail
            p = v.getPipeline(long(wf_info['wf_id']))

            if p:
                wi = indexworkflow.WorkflowIndexer()
                wi.index_vt_wf(wf_info, p)
                wi.close()
                result = ''
            else:
                result = "Error: Pipeline was not materialized"
                self.server_logger.info(result)
        except Exception, e:
            result = "Error: %s"%str(e)
            self.server_logger.info(result)
        return result
    
    def get_tag_version(self, host, port, db_name, vt_id, vt_tag):
        self.server_logger.info("Request: get_tag_version(%s,%s,%s,%s,%s)"%(host,
                                                                 port,
                                                                 db_name,
                                                                 vt_id,
                                                                 vt_tag))
        version = -1
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)

            (v, _ , _)  = io.load_vistrail(locator)
            if v.has_tag_str(vt_tag):
                version = v.get_tag_str(vt_tag).action_id
            self.server_logger.info("Answer: %s"%version)

        except Exception, e:
            self.server_logger.info("Error: %s"%str(e))

        return version
                      
                      
    def get_vt_xml(self, host, port, db_name, vt_id):
        self.server_logger.info("Request: get_vt_xml(%s,%s,%s,%s)"%(host,
                                                                 port,
                                                                 db_name,
                                                                 vt_id))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)

            (v, _ , _)  = io.load_vistrail(locator)
            result = io.serialize(v)
            self.server_logger.info("SUCCESS!")
            return result
        except Exception, e:
            self.server_logger.info("Error: %s"%str(e))
            return "FAILURE: %s" %str(e)
        
    def get_wf_xml(self, host, port, db_name, vt_id, version):
        self.server_logger.info("Request: get_wf_xml(%s,%s,%s,%s,%s)"%(host,
                                                                       port,
                                                                       db_name,
                                                                       vt_id,
                                                                       version))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)

            print "start"
            (v, _ , _)  = io.load_vistrail(locator)
            print "v is setup"
            p = v.getPipeline(long(version))
            print "pipeline setup"
            if p:
                result = io.serialize(p)
                print "pipeline serialized"
            else:
                result = "Error: Pipeline was not materialized"
                self.server_logger.info(result)
        except Exception, e:
            result = "get_wf_xml Error: %s"%str(e)
            self.server_logger.info(result)

        return result

    def get_wf_graph_pdf(self, host, port, db_name, vt_id, version):
        """get_wf_graph_pdf(host:str, port:int, db_name:str, vt_id:int, 
                          version:int) -> str
         Returns the relative url to the generated PDF
         """
        self.server_logger.info( "get_wf_graph_pdf(%s,%s,%s,%s,%s) request received"%(host,
                                                                                    port,
                                                                                    db_name,
                                                                                    vt_id,
                                                                                    version))
        print "get_wf_graph_pdf(%s,%s,%s,%s,%s) request received"%(host,
                                                      port,
                                                      db_name,
                                                      vt_id,
                                                      version)
        try:
            vt_id = long(vt_id)
            version = long(version)            
            subdir = 'workflows'
            filepath = os.path.join('/server/crowdlabs/site_media/media/graphs',
                                  subdir)
            base_fname = "graph_%s_%s.pdf" % (vt_id, version)
            filename = os.path.join(filepath,base_fname)
            if ((not os.path.exists(filepath) or
                os.path.exists(filepath) and not os.path.exists(filename)) 
                and self.proxies_queue is not None):
                #this server can send requests to other instances
                proxy = self.proxies_queue.get()
                try:
                    print "Sending request to ", proxy
                    result = proxy.get_wf_graph_pdf(host,port,db_name, vt_id, version)
                    self.proxies_queue.put(proxy)
                    print "returning %s"% result
                    self.server_logger.info("returning %s"% result)
                    return result
                except Exception, e:
                    print "Exception: ", str(e)
                    return ""
            
            if not os.path.exists(filepath):
                os.mkdir(filepath)
           
            if not os.path.exists(filename):
                locator = DBLocator(host=host,
                                    port=port,
                                    database=db_name,
                                    user=db_read_user,
                                    passwd=db_read_pass,
                                    obj_id=vt_id,
                                    obj_type=None,
                                    connection_id=None)

                (v, abstractions , thumbnails)  = io.load_vistrail(locator)
                controller = VistrailController()
                controller.set_vistrail(v, locator, abstractions, thumbnails)
                controller.change_selected_version(version)

                p = controller.current_pipeline
                from gui.pipeline_view import QPipelineView
                pipeline_view = QPipelineView()
                pipeline_view.scene().setupScene(p)
                pipeline_view.scene().saveToPDF(filename)
                del pipeline_view
            else:
                print "found cached pdf: ", filename
            return os.path.join(subdir,base_fname)
        except Exception, e:
            print "Error when saving pdf: ", str(e)
            return ""

    def get_wf_graph_png(self, host, port, db_name, vt_id, version):
        """get_wf_graph_png(host:str, port:int, db_name:str, vt_id:int, 
                          version:int) -> str
         Returns the relative url to the generated image
         """
        self.server_logger.info( "get_wf_graph_png(%s,%s,%s,%s,%s) request received"%(host,
                                                                                    port,
                                                                                    db_name,
                                                                                    vt_id,
                                                                                    version))
        print "get_wf_graph_png(%s,%s,%s,%s,%s) request received"%(host,
                                                      port,
                                                      db_name,
                                                      vt_id,
                                                      version)
        try:
            vt_id = long(vt_id)
            version = long(version)            
            subdir = 'workflows'
            filepath = os.path.join('/server/crowdlabs/site_media/media/graphs',
                                  subdir)
            base_fname = "graph_%s_%s.png" % (vt_id, version)
            filename = os.path.join(filepath,base_fname)
            if ((not os.path.exists(filepath) or
                os.path.exists(filepath) and not os.path.exists(filename)) 
                and self.proxies_queue is not None):
                #this server can send requests to other instances
                proxy = self.proxies_queue.get()
                try:
                    print "Sending request to ", proxy
                    result = proxy.get_wf_graph_png(host, port, db_name, vt_id, version)
                    self.proxies_queue.put(proxy)
                    print "returning %s"% result
                    self.server_logger.info("returning %s"% result)
                    return result
                except Exception, e:
                    print "Exception: ", str(e)
                    return ""
            #if it gets here, this means that we will execute on this instance
            if not os.path.exists(filepath):
                os.mkdir(filepath)

            if not os.path.exists(filename):
                locator = DBLocator(host=host,
                                    port=port,
                                    database=db_name,
                                    user=db_read_user,
                                    passwd=db_read_pass,
                                    obj_id=vt_id,
                                    obj_type=None,
                                    connection_id=None)
                (v, abstractions , thumbnails)  = io.load_vistrail(locator)
                controller = VistrailController()
                controller.set_vistrail(v, locator, abstractions, thumbnails)
                controller.change_selected_version(version)
                p = controller.current_pipeline
                from gui.pipeline_view import QPipelineView
                pipeline_view = QPipelineView()
                pipeline_view.scene().setupScene(p)
                pipeline_view.scene().saveToPNG(filename,1600)
                del pipeline_view
            else:
                print "Found cached image: ", filename
            return os.path.join(subdir,base_fname)
        except Exception, e:
            print "Error when saving png: ", str(e)
            
    def get_vt_graph_png(self, host, port, db_name, vt_id):
        """get_vt_graph_png(host:str, port: str, db_name: str, vt_id:str) -> str
        Returns the relative url of the generated image
        
        """
        try:
            vt_id = long(vt_id) 
            subdir = 'vistrails'
            filepath = os.path.join('/server/crowdlabs/site_media/media/graphs',
                                  subdir)
            base_fname = "graph_%s.png" % (vt_id)
            filename = os.path.join(filepath,base_fname)
            if ((not os.path.exists(filepath) or
                os.path.exists(filepath) and not os.path.exists(filename)) 
                and self.proxies_queue is not None):
                #this server can send requests to other instances
                proxy = self.proxies_queue.get()
                try:
                    print "Sending request to ", proxy
                    result = proxy.get_vt_graph_png(host, port, db_name, vt_id)
                    self.proxies_queue.put(proxy)
                    print "returning %s"% result
                    self.server_logger.info("returning %s"% result)
                    return result
                except Exception, e:
                    print "Exception: ", str(e)
                    return ""
            #if it gets here, this means that we will execute on this instance
            if not os.path.exists(filepath):
                os.mkdir(filepath)

            if not os.path.exists(filename):
                locator = DBLocator(host=host,
                                    port=port,
                                    database=db_name,
                                    user=db_read_user,
                                    passwd=db_read_pass,
                                    obj_id=vt_id,
                                    obj_type=None,
                                    connection_id=None)
                (v, abstractions , thumbnails)  = io.load_vistrail(locator)
                controller = VistrailController()
                controller.set_vistrail(v, locator, abstractions, thumbnails)
                from gui.version_view import QVersionTreeView
                version_view = QVersionTreeView()
                version_view.scene().setupScene(controller)
                version_view.scene().saveToPNG(filename,1600)
                del version_view
            else:
                print "Found cached image: ", filename
            return os.path.join(subdir,base_fname)
        except Exception, e:
            print "Error when saving png: ", str(e)        
            return ""

    def getPDFWorkflowMedley(self, m_id):
        """getPDFWorkflowMedley(m_id:int) -> str
        Returns the relative url to the generated image
        """
        self.server_logger.info( "getPDFWorkflowMedley(%s) request received"%m_id)
        print "getPDFWorkflowMedley(%s) request received"%m_id
        try:
            m_id = int(m_id)
            medley = self.medley_objs[m_id]
        except Exception, e:
            print str(e)

        try:
            locator = DBLocator(host=db_host,
                                        port=3306,
                                        database='vistrails',
                                        user='vtserver',
                                        passwd='',
                                        obj_id=medley._vtid,
                                        obj_type=None,
                                        connection_id=None)

            version = long(medley._version)
            subdir = os.path.join('workflows',
                     hashlib.sha224("%s_%s"%(str(locator),version)).hexdigest())
            filepath = os.path.join('/server/crowdlabs/site_media/media/medleys/images',
                                  subdir)
            base_fname = "%s_%s.pdf" % (str(locator.short_name), version)
            filename = os.path.join(filepath,base_fname)
            if ((not os.path.exists(filepath) or
                os.path.exists(filepath) and not os.path.exists(filename)) 
                and self.proxies_queue is not None):
                #this server can send requests to other instances
                proxy = self.proxies_queue.get()
                try:
                    print "Sending request to ", proxy
                    result = proxy.getPDFWorkflowMedley(m_id)
                    self.proxies_queue.put(proxy)
                    print "returning %s"% result
                    self.server_logger.info("returning %s"% result)
                    return result
                except Exception, e:
                    print "Exception: ", str(e)
                    return ""
            
            if not os.path.exists(filepath):
                os.mkdir(filepath)
           
            if not os.path.exists(filename):
                (v, abstractions , thumbnails)  = io.load_vistrail(locator)
                controller = VistrailController()
                controller.set_vistrail(v, locator, abstractions, thumbnails)
                controller.change_selected_version(version)

                print medley._vtid, " ", medley._version
                p = controller.current_pipeline
                from gui.pipeline_view import QPipelineView
                pipeline_view = QPipelineView()
                pipeline_view.scene().setupScene(p)
                pipeline_view.scene().saveToPDF(filename)
                del pipeline_view
            else:
                print "found cached pdf: ", filename
            return os.path.join(subdir,base_fname)
        except Exception, e:
            print "Error when saving pdf: ", str(e)
            return ""

    def getPNGWorkflowMedley(self, m_id):
        self.server_logger.info( "getPNGWorkflowMedley(%s) request received"%m_id)
        print "getPNGWorkflowMedley(%s) request received"%m_id
        try:
            m_id = int(m_id)
            medley = self.medley_objs[m_id]
        except Exception, e:
            print str(e)

        try:
            locator = DBLocator(host=db_host,
                                        port=3306,
                                        database='vistrails',
                                        user=db_read_user,
                                        passwd=db_read_pass,
                                        obj_id=medley._vtid,
                                        obj_type=None,
                                        connection_id=None)

            version = long(medley._version)
            subdir = os.path.join('workflows',
                     hashlib.sha224("%s_%s"%(str(locator),version)).hexdigest())
            filepath = os.path.join('/server/crowdlabs/site_media/media/medleys/images',
                                  subdir)
            base_fname = "%s_%s.png" % (str(locator.short_name), version)
            filename = os.path.join(filepath,base_fname)
            
            if ((not os.path.exists(filepath) or
                os.path.exists(filepath) and not os.path.exists(filename)) 
                and self.proxies_queue is not None):
                #this server can send requests to other instances
                proxy = self.proxies_queue.get()
                try:
                    print "Sending request to ", proxy
                    result = proxy.getPNGWorkflowMedley(m_id)
                    self.proxies_queue.put(proxy)
                    print "returning %s"% result
                    self.server_logger.info("returning %s"% result)
                    return result
                except Exception, e:
                    print "Exception: ", str(e)
                    return ""
            #if it gets here, this means that we will execute on this instance
            if not os.path.exists(filepath):
                os.mkdir(filepath)

            if not os.path.exists(filename):
                (v, abstractions , thumbnails)  = io.load_vistrail(locator)
                controller = VistrailController()
                controller.set_vistrail(v, locator, abstractions, thumbnails)
                controller.change_selected_version(version)

                print medley._vtid, " ", medley._version
                p = controller.current_pipeline
                from gui.pipeline_view import QPipelineView
                pipeline_view = QPipelineView()
                pipeline_view.scene().setupScene(p)
                pipeline_view.scene().saveToPNG(filename)
                del pipeline_view
            else:
                print "Found cached image: ", filename
            return os.path.join(subdir,base_fname)
        except Exception, e:
            print "Error when saving png: ", str(e)
	    return ""            
            
    def get_vt_zip(self, host, port, db_name, vt_id):
        """get_vt_zip(host:str, port: str, db_name: str, vt_id:str) -> str
        Returns a .vt file encoded as base64 string
        
        """
        self.server_logger.info("Request: get_vt_zip(%s,%s,%s,%s)"%(host,
                                                                 port,
                                                                 db_name,
                                                                 vt_id))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)
            save_bundle = locator.load()
            #annotate the vistrail
            save_bundle.vistrail.update_checkout_version('vistrails')
            #create temporary file
            (fd, name) = tempfile.mkstemp(prefix='vt_tmp',
                                          suffix='.vt')
            os.close(fd)
            fileLocator = FileLocator(name)
            fileLocator.save(save_bundle)
            contents = open(name).read()
            result = base64.b64encode(contents)
            os.unlink(name)
            self.server_logger.info("SUCCESS!")
            return result
        except Exception, e:
            self.server_logger.info("Error: %s"%str(e))
            return "FAILURE: %s" %str(e)
        
    def get_wf_vt_zip(self, host, port, db_name, vt_id, version):
        """get_wf_vt_zip(host:str, port:str, db_name:str, vt_id:str,
                         version:str) -> str
        Returns a vt file containing the single workflow defined by version 
        encoded as base64 string
        
        """
        self.server_logger.info("Request: get_wf_vt_zip(%s,%s,%s,%s,%s)"%(host,
                                                                       port,
                                                                       db_name,
                                                                       vt_id,
                                                                       version))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)
        
            (v, _ , _)  = io.load_vistrail(locator)
            p = v.getPipeline(long(version))
            if p:
                vistrail = Vistrail()
                action_list = []
                for module in p.module_list:
                    action_list.append(('add', module))
                for connection in p.connection_list:
                    action_list.append(('add', connection))
                action = core.db.action.create_action(action_list)
                vistrail.add_action(action, 0L)
                vistrail.addTag("Imported workflow", action.id)
                if not vistrail.db_version:
                    vistrail.db_version = currentVersion
                pipxmlstr = io.serialize(vistrail)
                result = base64.b64encode(pipxmlstr)
            else:
                result = "Error: Pipeline was not materialized"
                self.server_logger.info(result)
        except Exception, e:
            result = "Error: %s"%str(e)
            self.server_logger.info(result)
            
        return result

    def get_db_vt_list(self, host, port, db_name):
        self.server_logger.info("Request: get_db_vistrail_list(%s,%s,%s)"%(host,
                                                                 port,
                                                                 db_name))
        print "get_db_vt_list"
        config = {}
        config['host'] = host
        config['port'] = int(port)
        config['db'] = db_name
        config['user'] = db_read_user
        config['passwd'] = db_read_pass
        try:
            rows = io.get_db_vistrail_list(config)
            print "returning ", rows
            return rows
        except Exception, e:
            self.server_logger.info("Error: %s"%str(e))
            print "Error: ", str(e)
            return "FAILURE: %s" %str(e)
        
    def get_db_vt_list_xml(self, host, port, db_name):
        self.server_logger.info("Request: get_db_vistrail_list(%s,%s,%s)"%(host,
                                                                 port,
                                                                 db_name))
        config = {}
        config['host'] = host
        config['port'] = int(port)
        config['db'] = db_name
        config['user'] = db_read_user
        config['passwd'] = db_read_pass
        try:
            rows = io.get_db_vistrail_list(config)
            result = '<vistrails>'
            for (id, name, mod_time) in rows:
                result += '<vistrail id="%s" name="%s" mod_time="%s" />'%(id,name,mod_time)
            result += '</vistrails>'
            return result
        except Exception, e:
            self.server_logger.info("Error: %s"%str(e))
            return "FAILURE: %s" %str(e)

    def get_vt_tagged_versions(self, host, port, db_name, vt_id):
        self.server_logger.info("Request: get_vt_tagged_versions(%s,%s,%s,%s)"%(host,
                                                                 port,
                                                                 db_name,
                                                                 vt_id))
        try:
            locator = DBLocator(host=host,
                                port=int(port),
                                database=db_name,
                                user=db_read_user,
                                passwd=db_read_pass,
                                obj_id=int(vt_id),
                                obj_type=None,
                                connection_id=None)

            result = []
            v = locator.load().vistrail
            for elem, tag in v.get_tagMap().iteritems():
                action_map = v.actionMap[long(elem)]
                if v.get_thumbnail(elem):
                    thumbnail_fname = os.path.join(
                        get_vistrails_configuration().thumbs.cacheDirectory,
                        v.get_thumbnail(elem))
                else:
                    thumbnail_fname = ""
                result.append({'id': elem, 'name': tag,
                               'notes': v.get_notes(elem) or '',
                               'user':action_map.user or '', 
                               'date':action_map.date,
                               'thumbnail': thumbnail_fname})
            self.server_logger.info("SUCCESS!")
            return result
        except Exception, e:
            self.server_logger.info("Error: %s"%str(e))
            return "FAILURE: %s" %str(e)
################################################################################                           
# Some Medley code
class XMLObject(object):
    @staticmethod
    def convert_from_str(value, type):
        def bool_conv(x):
            s = str(x).upper()
            if s == 'TRUE':
                return True
            if s == 'FALSE':
                return False

        if value is not None:
            if type == 'str':
                return str(value)
            elif value.strip() != '':
                if type == 'long':
                    return long(value)
                elif type == 'float':
                    return float(value)
                elif type == 'int':
                    return int(value)
                elif type == 'bool':
                    return bool_conv(value)
                elif type == 'date':
                    return date(*strptime(value, '%Y-%m-%d')[0:3])
                elif type == 'datetime':
                    return datetime(*strptime(value, '%Y-%m-%d %H:%M:%S')[0:6])
        return None

    @staticmethod
    def convert_to_str(value,type):
        if value is not None:
            if type == 'date':
                return value.isoformat()
            elif type == 'datetime':
                return value.strftime('%Y-%m-%d %H:%M:%S')
            else:
                return str(value)
        return ''

################################################################################

class MedleySimpleGUI(XMLObject):
    def __init__(self, id, name, vtid=None, version=None, alias_list=None, 
                 t='vistrail', has_seq=None):
        self._id = id
        self._name = name
        self._version = version
        self._alias_list = alias_list
        self._vtid = vtid
        self._type = t

        if has_seq == None:
            self._has_seq = False
            if type(self._alias_list) == type({}):
                for v in self._alias_list.itervalues():
                    if v._component._seq == True:
                        self._has_seq = True
        else:
            self._has_seq = has_seq

    def to_xml(self, node=None):
        """to_xml(node: ElementTree.Element) -> ElementTree.Element
           writes itself to xml
        """

        if node is None:
            node = ElementTree.Element('medley_simple_gui')

        #set attributes
        node.set('id', self.convert_to_str(self._id,'long'))
        node.set('version', self.convert_to_str(self._version,'long'))
        node.set('vtid', self.convert_to_str(self._vtid,'long'))
        node.set('name', self.convert_to_str(self._name,'str'))
        node.set('type', self.convert_to_str(self._type,'str'))
        node.set('has_seq', self.convert_to_str(self._has_seq,'bool'))
        for (k,v) in self._alias_list.iteritems():
            child_ = ElementTree.SubElement(node, 'alias')
            v.to_xml(child_)
        return node

    @staticmethod
    def from_xml(node):
        if node.tag != 'medley_simple_gui':
            print "node.tag != 'medley_simple_gui'"
            return None
        #read attributes
        data = node.get('id', None)
        id = MedleySimpleGUI.convert_from_str(data, 'long')
        data = node.get('name', None)
        name = MedleySimpleGUI.convert_from_str(data, 'str')
        data = node.get('version', None)
        version = MedleySimpleGUI.convert_from_str(data, 'long')
        data = node.get('vtid', None)
        vtid = MedleySimpleGUI.convert_from_str(data, 'long')
        data = node.get('type', None)
        type = MedleySimpleGUI.convert_from_str(data, 'str')
        data = node.get('has_seq', None)
        seq = ComponentSimpleGUI.convert_from_str(data, 'bool')
        alias_list = {}
        for child in node.getchildren():
            if child.tag == "alias":
                alias = AliasSimpleGUI.from_xml(child)
                alias_list[alias._name] = alias
        return MedleySimpleGUI(id=id, name=name, vtid=vtid, version=version, 
                               alias_list=alias_list, t=type, has_seq=seq)

################################################################################

class AliasSimpleGUI(XMLObject):
    def __init__(self, id, name, component=None):
        self._id = id
        self._name = name
        self._component = component

    def to_xml(self, node=None):
        """to_xml(node: ElementTree.Element) -> ElementTree.Element
            writes itself to xml
        """
        if node is None:
            node = ElementTree.Element('alias')

        #set attributes
        node.set('id', self.convert_to_str(self._id,'long'))
        node.set('name', self.convert_to_str(self._name,'str'))
        child_ = ElementTree.SubElement(node, 'component')
        self._component.to_xml(child_)

        return node

    @staticmethod
    def from_xml(node):
        if node.tag != 'alias':
            return None

        #read attributes
        data = node.get('id', None)
        id = AliasSimpleGUI.convert_from_str(data, 'long')
        data = node.get('name', None)
        name = AliasSimpleGUI.convert_from_str(data, 'str')
        for child in node.getchildren():
            if child.tag == "component":
                component = ComponentSimpleGUI.from_xml(child)
        alias = AliasSimpleGUI(id,name,component)
        return alias

################################################################################

class ComponentSimpleGUI(XMLObject):
    def __init__(self, id, pos, ctype, spec, val=None, minVal=None, maxVal=None,
                 stepSize=None, strvalueList="", parent=None, seq=False, 
                 widget="text"):
        """ComponentSimpleGUI() 
        widget can be: text, slider, combobox, numericstepper, checkbox

        """
        self._id = id
        self._pos = pos
        self._spec = spec
        self._ctype = ctype
        self._val = val
        self._minVal = minVal
        self._maxVal = maxVal
        self._stepSize = stepSize
        self._strvaluelist = strvalueList
        self._parent = parent
        self._seq = seq
        self._widget = widget

    def _get_valuelist(self):
        data = self._strvaluelist.split(',')
        result = []
        for d in data:
            result.append(urllib.unquote_plus(d))
        return result
    def _set_valuelist(self, valuelist):
        q = []
        for v in valuelist:
            q.append(urllib.quote_plus(v))
        self._strvaluelist = ",".join(q)

    _valueList = property(_get_valuelist,_set_valuelist)

    def to_xml(self, node=None):
        """to_xml(node: ElementTree.Element) -> ElementTree.Element
             writes itself to xml
        """
        if node is None:
            node = ElementTree.Element('component')

        #set attributes
        node.set('id', self.convert_to_str(self._id,'long'))
        node.set('pos', self.convert_to_str(self._pos,'long'))
        node.set('spec', self.convert_to_str(self._spec,'str'))
        node.set('ctype', self.convert_to_str(self._ctype,'str'))
        node.set('val', self.convert_to_str(self._val, 'str'))
        node.set('minVal', self.convert_to_str(self._minVal,'str'))
        node.set('maxVal', self.convert_to_str(self._maxVal,'str'))
        node.set('stepSize', self.convert_to_str(self._stepSize,'str'))
        node.set('valueList',self.convert_to_str(self._strvaluelist,'str'))
        node.set('parent', self.convert_to_str(self._parent,'str'))
        node.set('seq', self.convert_to_str(self._seq,'bool'))
        node.set('widget',self.convert_to_str(self._widget,'str'))
        return node

    @staticmethod
    def from_xml(node):
        if node.tag != 'component':
            return None

        #read attributes
        data = node.get('id', None)
        id = ComponentSimpleGUI.convert_from_str(data, 'long')
        data = node.get('pos', None)
        pos = ComponentSimpleGUI.convert_from_str(data, 'long')
        data = node.get('ctype', None)
        ctype = ComponentSimpleGUI.convert_from_str(data, 'str')
        data = node.get('spec', None)
        spec = ComponentSimpleGUI.convert_from_str(data, 'str')
        data = node.get('val', None)
        val = ComponentSimpleGUI.convert_from_str(data, 'str')
        val = val.replace("&lt;", "<")
        val = val.replace("&gt;", ">")
        val = val.replace("&amp;","&")
        data = node.get('minVal', None)
        minVal = ComponentSimpleGUI.convert_from_str(data, 'str')
        data = node.get('maxVal', None)
        maxVal = ComponentSimpleGUI.convert_from_str(data, 'str')
        data = node.get('stepSize', None)
        stepSize = ComponentSimpleGUI.convert_from_str(data, 'str')
        data = node.get('valueList', None)
        values = ComponentSimpleGUI.convert_from_str(data, 'str')
        values = values.replace("&lt;", "<")
        values = values.replace("&gt;", ">")
        values = values.replace("&amp;","&")
        data = node.get('parent', None)
        parent = ComponentSimpleGUI.convert_from_str(data, 'str')
        data = node.get('seq', None)
        seq = ComponentSimpleGUI.convert_from_str(data, 'bool')
        data = node.get('widget', None)
        widget = ComponentSimpleGUI.convert_from_str(data, 'str')
        component = ComponentSimpleGUI(id=id,
                                       pos=pos,
                                       ctype=ctype,
                                       spec=spec,
                                       val=val,
                                       minVal=minVal,
                                       maxVal=maxVal,
                                       stepSize=stepSize,
                                       strvalueList=values,
                                       parent=parent,
                                       seq=seq,
                                       widget=widget)
        return component

################################################################################
################################################################################

class VistrailsServerSingleton(VistrailsApplicationInterface,
                               QtGui.QApplication):
    """
    VistrailsServerSingleton is the singleton of the application,
    there will be only one instance of the application during VisTrails

    """
    def __call__(self):
        """ __call__() -> VistrailsServerSingleton
        Return self for calling method

        """
        if not self._initialized:
            self.init()
        return self

    def __init__(self):
        QtGui.QApplication.__init__(self, sys.argv)
        VistrailsApplicationInterface.__init__(self)
        if QtCore.QT_VERSION < 0x40200: # 0x40200 = 4.2.0
            raise core.requirements.MissingRequirement("Qt version >= 4.2")
        
        self.rpcserver = None
        self.images_url = "http://vistrails.sci.utah.edu/medleys/images/"
        self.temp_xml_rpc_options = InstanceObject(server=None,
                                                   port=None,
                                                   log_file=None)

        qt.allowQObjects()

    def make_logger(self, filename):
        """self.make_logger(filename:str) -> logger. Creates a logging object to
        be used for the server so we can log requests in file f."""
        f = open(filename, 'a')
        logger = logging.getLogger("VistrailsRPC")
        handler = logging.StreamHandler(f)
        handler.setFormatter(logging.Formatter('VisTrails RPC - %(asctime)s %(levelname)-8s %(message)s'))
        handler.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        return logger

    def init(self, optionsDict=None):
        """ init(optionDict: dict) -> boolean
        Create the application with a dict of settings

        """
        VistrailsApplicationInterface.init(self,optionsDict)

        self.vistrailsStartup.init()
        print self.temp_xml_rpc_options.log_file
        self.server_logger = self.make_logger(self.temp_xml_rpc_options.log_file)
        self.start_other_instances(self.temp_xml_rpc_options.instances)
        self._python_environment = self.vistrailsStartup.get_python_environment()
        self._initialized = True
        return True

    def start_other_instances(self, number):
        self.others = []
        host = self.temp_xml_rpc_options.server
        port = self.temp_xml_rpc_options.port
        virtual_display = 6
        script = '/server/vistrails/trunk/scripts/start_vistrails.sh'
        for x in xrange(number):
            port += 1
            virtual_display += 1
            args = [script,":%s"%virtual_display,host,str(port),'0', '0']
            try:
                p = subprocess.Popen(args)
                time.sleep(20)
                self.others.append("http://%s:%s"%(host,port))
            except Exception, e:
                print "Couldn't start the instance on display :", virtual_display, " port: ",port
                print "Exception: ", str(e)
                 
    def stop_other_instances(self): 
        script = '/server/vistrails/trunk/vistrails/stop_vistrails_server.py'
        for o in self.others:
            args = ['python', script, o]
            try:
                subprocess.Popen(args)
                time.sleep(15)
            except Exception, e:
                print "Couldn't stop instance: ", o
                print "Exception: ", str(e)
                       
    def run_server(self):
        """run_server() -> None
        This will run forever until the server receives a quit request, done
        via xml-rpc.

        """
        print "Server is running on http://%s:%s"%(self.temp_xml_rpc_options.server,
                                                   self.temp_xml_rpc_options.port),
        if self.temp_xml_rpc_options.multithread:
            self.rpcserver = ThreadedXMLRPCServer((self.temp_xml_rpc_options.server,
                                                   self.temp_xml_rpc_options.port))
            print " multithreaded"
        else:
            self.rpcserver = StoppableXMLRPCServer((self.temp_xml_rpc_options.server,
                                                   self.temp_xml_rpc_options.port))
            print " singlethreaded" 
        #self.rpcserver.register_introspection_functions()
        self.rpcserver.register_instance(RequestHandler(self.server_logger,
                                                        self.others))
        self.rpcserver.register_function(self.quit_server, "quit")
        self.server_logger.info("Vistrails XML RPC Server is listening on http://%s:%s"% \
                        (self.temp_xml_rpc_options.server,
                         self.temp_xml_rpc_options.port))
        self.rpcserver.serve_forever()
        self.rpcserver.server_close()
        return 0
    
    def quit_server(self):
        result = "Vistrails XML RPC Server is quitting."
        self.stop_other_instances()
        self.server_logger.info(result)
        self.rpcserver.stop = True
        return result
                
    def setupOptions(self):
        """ setupOptions() -> None
        Check and store all command-line arguments

        """
        add = command_line.CommandLineParser.add_option

        add("-T", "--xml_rpc_server", action="store", dest="rpcserver",
            help="hostname or ip address where this xml rpc server will work")
        add("-R", "--xml_rpc_port", action="store", type="int", default=8080,
            dest="rpcport", help="database port")
        add("-L", "--xml_rpc_log_file", action="store", dest="rpclogfile",
            default=os.path.join(system.vistrails_root_directory(),
                                 'rpcserver.log'),
            help="log file for XML RPC server")
        add("-O", "--xml_rpc_instances", action="store", type='int', default=0,
            dest="rpcinstances",
            help="number of other instances that vistrails should start")
        add("-M", "--multithreaded", action="store_true",
            default = None, dest='multithread',
            help="server will start a thread for each request")
        VistrailsApplicationInterface.setupOptions(self)

    def readOptions(self):
        """ readOptions() -> None
        Read arguments from the command line

        """
        get = command_line.CommandLineParser().get_option
        self.temp_xml_rpc_options = InstanceObject(server=get('rpcserver'),
                                                   port=get('rpcport'),
                                                   log_file=get('rpclogfile'),
                                                   instances=get('rpcinstances'),
                                                   multithread=get('multithread'))
        VistrailsApplicationInterface.readOptions(self)



# The initialization must be explicitly signalled. Otherwise, any
# modules importing vis_application will try to initialize the entire
# app.
def start_server(optionsDict=None):
    """Initializes the application singleton."""
    global VistrailsServer
    if VistrailsServer:
        print "Server already started."""
        return
    VistrailsServer = VistrailsServerSingleton()
    try:
        core.requirements.check_all_vistrails_requirements()
    except core.requirements.MissingRequirement, e:
        msg = ("VisTrails requires %s to properly run.\n" %
               e.requirement)
        print msg
        sys.exit(1)
    x = VistrailsServer.init(optionsDict)
    if x == True:
        return 0
    else:
        return 1

VistrailsServer = None

def stop_server():
    """Stop and finalize the application singleton."""
    global VistrailsServer
    VistrailsServer.save_configuration()
    VistrailsServer.destroy()
    VistrailsServer.deleteLater()
