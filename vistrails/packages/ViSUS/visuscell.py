from info import identifier
from PyQt4 import QtGui,QtCore
from core.modules.vistrails_module import Module, ModuleError, NotCacheable
from core.modules.module_registry import get_module_registry
from packages.spreadsheet.basic_widgets import SpreadsheetCell, CellLocation
from packages.spreadsheet.spreadsheet_cell import QCellWidget

# Needed for configuration
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from gui.modules.module_configure import StandardModuleConfigurationWidget

# Needed for port related stuff
from core.vistrail.port import PortEndPoint
import core.modules.basic_modules as basic_modules

from packages.uvcdat.init import Variable, Plot
from packages.uvcdat_cdms.init import CDMSVariable
from packages.uvcdat.init import expand_port_specs as _expand_port_specs

import sys
import visuspy
import sip

from core.modules.vistrails_module import Module, NotCacheable, ModuleError
from packages.spreadsheet.spreadsheet_base import (StandardSheetReference,
                              StandardSingleCellSheetReference)
from packages.spreadsheet.spreadsheet_controller import spreadsheetController
from packages.spreadsheet.spreadsheet_event import DisplayCellEvent


# //////////////////////////////////////////////////////// 
VisusShowAdvanced  =True
VisusGlobalInstance={}

# //////////////////////////////////////////////////////// 
class VisusViewer():

    #statics
    VisusLaunched=False
    VisusGuiApp=0

    #InitializeVisus
    @staticmethod
    def InitializeVisus():
        #print "__InitializeVisus__"
        if VisusViewer.VisusLaunched == False:
            VisusViewer.VisusGuiApp=visuspy.GuiApplication()
            VisusViewer.VisusGuiApp.setCommandLine("ViSUS for UV-CDAT")
            visuspy.ENABLE_VISUS_APPKIT()	
            VisusViewer.VisusGuiApp.onInit()
            VisusViewer.VisusLaunched = True

    #CleanupVisus
    @staticmethod
    def CleanupVisus():
        #print "__CleanupVisus__"
        VisusViewer.VisusGuiApp=None
        VisusViewer.VisusLaunched=False
        visuspy.GLCanvas.setShared(None)

    # constructor
    def __init__(self):
        VisusViewer.InitializeVisus()
        self.createViewer()

    # notOwned
    def notOwned(self,component):  
        return sip.wrapinstance(component.sipHandle(),QtGui.QWidget)    
  
    # getCanvas
    def getCanvas(self):
        return self.notOwned(self.viewer.getGLCanvas())

    # createViewer
    def createViewer(self):
        self.viewer=visuspy.VisusViewer() 
        self.viewer.setVisible(False)
    
    #loc2str
    def loc2str(self,cellloc):
        return ' @ %s%s' % (chr(ord('A') + cellloc[1]),cellloc[0]+1)

    #showWindow
    def showWindow(self,component,desc="Visus",cellloc=(0,0),geom=(50,50,500,500)):
        window=QMainWindow()
        window.setWindowTitle(desc+self.loc2str(cellloc))
        window.setCentralWidget(component)
        window.setGeometry(geom[0],geom[1],geom[2],geom[3])
        window.setVisible(True)
        return window

    #showTreeview
    def showTreeview(self,loc):
        treeview=self.notOwned(self.viewer.getTreeView())
        self.treeview=self.showWindow(treeview,"Visus TreeView",loc,(50,50,300,700))

    #showDataflow
    def showDataflow(self,loc):
        dataflow=self.notOwned(self.viewer.getGraphview())
        self.dataflow=self.showWindow(dataflow,"Visus Dataflow",loc,(75,75,500,500))

    #showLog
    def showLog(self,loc):
        log=self.notOwned(self.viewer.getLog())
        self.log=self.showWindow(log,"Visus Log",loc,(25,25,600,400))

    #forceRefresh
    def forceRefresh(self):
        self.viewer.refreshDataNow()

    #is3D
    def is3D(self):
        return len(self.viewer.getRoot().getAllChilds("volume"))>0

    #open
    def open(self,dataset):
        path=self.server+"/mod_visus?dataset="+dataset
        print "VisusViewer: loading",path,"..."
        self.viewer.open(path)

    #showTimeSlider
    def showTimeSlider(self,cellloc=(0,0)):
        name='time'
        if self.raiseWindow(name):
            return
        desc="Visus Time"
        valuenode=self.viewer.getRoot().getAllChilds("time")[0]
        setattr(self,name,self.showEditor(valuenode,desc,cellloc,(100,100,300,220)))

    #showFieldname
    def showFieldname(self,kind,cellloc=(0,0)):
        name='fieldname_'+kind
        if self.raiseWindow(name):
            return
        desc="Fieldname (%s)"%kind
        valuenode=self.viewer.getRoot().getAllChilds(kind)[0].getChild("fieldname")
        setattr(self,name,self.showEditor(valuenode,desc,cellloc,(100,300,860,300)))

    #showPalette
    def showPalette(self,kind,cellloc=(0,0)):
        name='palette_'+kind
        if self.raiseWindow(name):
            return
        desc="Palette (%s)"%kind
        valuenode=self.viewer.getRoot().getAllChilds(kind)[0].getChild("palette")
        setattr(self,name,self.showEditor(valuenode,desc,cellloc,(150,150,300,275)))

    #showEditor
    def showEditor(self,valuenode,desc,cellloc=(0,0),geom=(50,50,300,400)):
        editor=valuenode.editable_value.get().createEditor()
        tabpanel=visuspy.TabPanel()
        tabpanel.addTab(desc+self.loc2str(cellloc),editor)
        window=visuspy.Window("ViSUS")
        window.setMainComponent(tabpanel)
        window.setBounds(geom[0],geom[1],geom[2],geom[3])
        window.setVisible(True)
        window.onclose.connect(visuspy.Slot0_void.New(self.editorClosed,self))  
        return window

    #editorClosed
    def editorClosed(self):
        component=visuspy.Signal.sender()
        components=['time','palette_slice','palette_volume','fieldname_slice','fieldname_volume']
        print "VisusViewer.editorClosed: trying to close ",component
        for c in components:
            if component==getattr(self,c):
                #setattr(self,c,None)
                return
        print "VisusViewer.editorClosed: unknown component",component

    #raiseWindow
    def raiseWindow(self,name):
        if hasattr(self,name):
            window=getattr(self,name)
            window.setVisible(True)
            window.bringToFront()
            return True
        return False

# //////////////////////////////////////////////////////// 
class VisusCell(SpreadsheetCell):
    def __init__(self):
        SpreadsheetCell.__init__(self)
        self.cellWidget = None
        self.location = None
        self.var = None

    def GetVars():
        return self.cellWidget

    def compute(self):
        """ compute() -> None
        Dispatch the QVisusWidget to do the actual rendering 
        """
        self.location = self.getInputFromPort("Location")
        self.var = self.getInputFromPort("variable")
        self.cellWidget = self.displayAndWait(QVisusWidget,(self.var,self.location))

# //////////////////////////////////////////////////////// 
class QVisusWidget(QCellWidget):
    def __init__(self, parent=None, f=QtCore.Qt.WindowFlags()):
        QCellWidget.__init__(self,parent,f)
        self.layout = QVBoxLayout(self)
        self.view = None
        self.location = None
        self.var = None

    def showEvent(self,event):
        if self.view is not None:
            self.view.setParent(self)
            self.view.show()
            self.layout.addWidget(self.view)

    def closeEvent(self,event):
        self.view=None
        self.viewer=None

    def hideEvent(self,event):
        if self.view is not None:
            self.view.setParent(None)
            self.view.hide()

    def LoadPlotError(self):
        QMessageBox.information(None, "ViSUS failed to load plot...", "ViSUS Failed to load plot.")

    def OpenUrl(self):
        if 'visus_idx' in self.var.attributes and 'visus_server' in self.var.attributes:
            self.viewer.server=self.var.attributes['visus_server']
            self.viewer.open(self.var.attributes['visus_idx'])
        else:
            self.LoadPlotError()

    def updateContents(self, inputPorts):
        try:
            self.updateVisus(inputPorts)
        except:
            QMessageBox.information(None,"Exception..","ViSUS has encountered an exception while processing")

    def updateVisus(self, inputPorts):
        (self.var,self.location) = inputPorts

        # find or create the visus instance associated with this cell
        global VisusGlobalInstance
        key=self.getKey()
        if key not in VisusGlobalInstance.keys():
            VisusGlobalInstance[key]=VisusViewer()
        self.viewer=VisusGlobalInstance[key]

        # add canvas to cell
        if self.view is None:
          self.view=self.viewer.getCanvas()
          self.layout.addWidget(self.view)

        # load url
        self.OpenUrl()
          
        QCellWidget.updateContents(self, inputPorts)

    def saveToPNG(self, filename):
        pass

    def dumpToFile(self,filename):
        pass

    def deleteLater(self):
        QCellWidget.deleteLater(self)

    def getKey(self):
        return str([self.location.row,self.location.col])

# //////////////////////////////////////////////////////// 
def registerSelf():
    registry = get_module_registry()

    registry.add_module(VisusCell, configureWidgetType=VisusCellConfigurationWidget)
    registry.add_input_port(VisusCell, "Location", CellLocation)
    registry.add_input_port(VisusCell, "variable", CDMSVariable)
    registry.add_output_port(VisusCell, "self", VisusCell)


# //////////////////////////////////////////////////////// 
class VisusConfigurationWidget(StandardModuleConfigurationWidget):

    newConfigurationWidget = None
    currentConfigurationWidget = None
    savingChanges = False

    def __init__(self, module, controller, title, parent=None):
        """ VisusConfigurationWidget(module: Module,
                                       controller: VistrailController,
                                       parent: QWidget)
                                       -> LayerConfigurationWidget
        Setup the dialog ...

        """

        StandardModuleConfigurationWidget.__init__(self, module, controller, parent)
        self.setWindowTitle( title )
        self.moduleId = module.id
        self.getParameters( module )
        self.createTabs()
        self.createLayout()
        self.addPortConfigTab()

        if ( VisusConfigurationWidget.newConfigurationWidget == None ): VisusConfigurationWidget.setupSaveConfigurations()
        VisusConfigurationWidget.newConfigurationWidget = self

    def destroy( self, destroyWindow = True, destroySubWindows = True):
        self.saveConfigurations()
        StandardModuleConfigurationWidget.destroy( self, destroyWindow, destroySubWindows )

    def sizeHint(self):
        return QSize(400,200)

    def createTabs( self ):
        self.setLayout( QVBoxLayout() )
        self.layout().setMargin(0)
        self.layout().setSpacing(0)

        self.tabbedWidget = QTabWidget()
        self.layout().addWidget( self.tabbedWidget )

    def addPortConfigTab(self):
        portConfigPanel = self.getPortConfigPanel()
        self.tabbedWidget.addTab( portConfigPanel, 'ports' )

    @staticmethod
    def setupSaveConfigurations():
        import api
        ctrl = api.get_current_controller()
        scene = ctrl.current_pipeline_view
        scene.connect( scene, SIGNAL('moduleSelected'), VisusConfigurationWidget.saveConfigurations )

    @staticmethod
    def saveConfigurations( newModuleId=None, selectedItemList=None ):
        rv = False
        if not VisusConfigurationWidget.savingChanges:
            if VisusConfigurationWidget.currentConfigurationWidget and VisusConfigurationWidget.currentConfigurationWidget.state_changed:
                rv = VisusConfigurationWidget.currentConfigurationWidget.askToSaveChanges()
            VisusConfigurationWidget.currentConfigurationWidget = VisusConfigurationWidget.newConfigurationWidget
        return rv

    @staticmethod
    def saveNewConfigurations():
        return False

    def getPortConfigPanel( self ):
        listContainer = QWidget( )
        listContainer.setLayout(QGridLayout(listContainer))
        listContainer.setFocusPolicy(Qt.WheelFocus)
        self.inputPorts = self.module.destinationPorts()
        self.inputDict = {}
        self.outputPorts = self.module.sourcePorts()
        self.outputDict = {}
        label = QLabel('Input Ports')
        label.setAlignment(Qt.AlignHCenter)
        label.font().setBold(True)
        label.font().setPointSize(12)
        listContainer.layout().addWidget(label, 0, 0)
        label = QLabel('Output Ports')
        label.setAlignment(Qt.AlignHCenter)
        label.font().setBold(True)
        label.font().setPointSize(12)
        listContainer.layout().addWidget(label, 0, 1)

        for i in xrange(len(self.inputPorts)):
            port = self.inputPorts[i]
            checkBox = self.checkBoxFromPort(port, True)
            checkBox.setFocusPolicy(Qt.StrongFocus)
            self.connect(checkBox, SIGNAL("stateChanged(int)"),
                         self.updateState)
            self.inputDict[port.name] = checkBox
            listContainer.layout().addWidget(checkBox, i+1, 0)

        for i in xrange(len(self.outputPorts)):
            port = self.outputPorts[i]
            checkBox = self.checkBoxFromPort(port)
            checkBox.setFocusPolicy(Qt.StrongFocus)
            self.connect(checkBox, SIGNAL("stateChanged(int)"),
                         self.updateState)
            self.outputDict[port.name] = checkBox
            listContainer.layout().addWidget(checkBox, i+1, 1)

        listContainer.adjustSize()
        listContainer.setFixedHeight(listContainer.height())
        return listContainer

    def closeEvent(self, event):
        self.askToSaveChanges()
        event.accept()

    def updateState(self, state):
        self.setFocus(Qt.MouseFocusReason)
        self.saveButton.setEnabled(True)
        self.resetButton.setEnabled(True)
        if not self.state_changed:
            self.state_changed = True
            self.emit(SIGNAL("stateChanged"))

    def saveTriggered(self, checked = False):
        self.okTriggered()
        for port in self.inputPorts:
            if (port.optional and
                self.inputDict[port.name].checkState()==Qt.Checked):
                self.module.visible_input_ports.add(port.name)
            else:
                self.module.visible_input_ports.discard(port.name)

        for port in self.outputPorts:
            if (port.optional and
                self.outputDict[port.name].checkState()==Qt.Checked):
                self.module.visible_output_ports.add(port.name)
            else:
                self.module.visible_output_ports.discard(port.name)
        self.saveButton.setEnabled(False)
        self.state_changed = False
        self.emit(SIGNAL("stateChanged"))

    def resetTriggered(self):
        self.startOver();
        self.setFocus(Qt.MouseFocusReason)
        self.setUpdatesEnabled(False)
        for i in xrange(len(self.inputPorts)):
            port = self.inputPorts[i]
            entry = (PortEndPoint.Destination, port.name)
            checkBox = self.inputDict[port.name]
            if not port.optional or entry in self.module.portVisible:
                checkBox.setCheckState(Qt.Checked)
            else:
                checkBox.setCheckState(Qt.Unchecked)
            if not port.optional or port.sigstring=='()':
                checkBox.setEnabled(False)
        for i in xrange(len(self.outputPorts)):
            port = self.outputPorts[i]
            entry = (PortEndPoint.Source, port.name)
            checkBox = self.outputDict[port.name]
            if not port.optional or entry in self.module.portVisible:
                checkBox.setCheckState(Qt.Checked)
            else:
                checkBox.setCheckState(Qt.Unchecked)
            if not port.optional:
                checkBox.setEnabled(False)
        self.setUpdatesEnabled(True)
        self.saveButton.setEnabled(True)
        self.resetButton.setEnabled(False)
        self.state_changed = False
        self.emit(SIGNAL("stateChanged"))

    def stateChanged(self, changed = True ):
        self.state_changed = changed
        self.saveButton.setEnabled(True)
        self.resetButton.setEnabled(True)
#        print " %s-> state changed: %s " % ( self.pmod.getName(), str(changed) )

    def getParameters( self, module ):
        pass

    def createLayout( self ):
        self.groupBox = QGroupBox()
        self.groupBoxLayout = QHBoxLayout(self.groupBox)
        self.fileLabel = QLabel("Filename: ")
        self.fileEntry = QLineEdit();
        self.groupBoxLayout.addWidget(self.fileLabel)
        self.groupBoxLayout.addWidget(self.fileEntry)

    def createButtonLayout(self):
        """ createButtonLayout() -> None
        Construct Save & Reset button

        """
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setMargin(5)
        self.saveButton = QPushButton('&Save', self)
        self.saveButton.setFixedWidth(100)
        self.saveButton.setEnabled(True)
        self.buttonLayout.addWidget(self.saveButton)
        self.resetButton = QPushButton('&Reset', self)
        self.resetButton.setFixedWidth(100)
        self.resetButton.setEnabled(True)
        self.buttonLayout.addWidget(self.resetButton)

        self.layout().addLayout(self.buttonLayout)
        self.connect(self.saveButton,SIGNAL('clicked(bool)'),  self.saveTriggered)
        self.connect(self.resetButton,SIGNAL('clicked(bool)'),  self.resetTriggered)
        self.setMouseTracking(True)
        self.setFocusPolicy( Qt.WheelFocus )

    def okTriggered(self):
        pass

    def checkBoxFromPort(self, port, input_=False):
        checkBox = QCheckBox(port.name)
        if input_:
            port_visible = port.name in self.module.visible_input_ports
        else:
            port_visible = port.name in self.module.visible_output_ports
        if not port.optional or port_visible:
            checkBox.setCheckState(Qt.Checked)
        else:
            checkBox.setCheckState(Qt.Unchecked)
        if not port.optional or (input_ and port.sigstring=='()'):
            checkBox.setEnabled(False)
        return checkBox

    def persistParameterList( self, parameter_list, **args ):
        #print self.module
        #self.module_descriptor.module.persistParameterList(parameter_list, **args)
        pass

class VisusCellConfigurationWidget(VisusConfigurationWidget):
    """
    VisusCellConfigurationWidget ...
    """

    def __init__(self, module, controller, parent=None):
        """ VisusCellConfigurationWidget(module: Module,
                                       controller: VistrailController,
                                       parent: QWidget)
        Setup the dialog ...
        """
        self.cellAddress = 'A1'
        VisusConfigurationWidget.__init__(self, module, controller, 'Visus Cell Configuration', parent)

    def getParameters( self, module ):
        pass

    def updateVistrail(self):
        pass

    def createLayout(self):
        #get the widget associated with this controller
        coords=self.controller.current_cell_coords
        self.viewerInstance = VisusGlobalInstance[str(coords)]

        VisusWidget = QWidget()
        #VisusWidget.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Preferred)
        self.tabbedWidget.addTab( VisusWidget, 'Visus' )

        self.layout0=QVBoxLayout()
        VisusWidget.setLayout(self.layout0)

        #button to open time slider
        self.timeWidget=QGroupBox('Date/Time Selection')
        #self.timeWidget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum)
        self.layout0.addWidget(self.timeWidget)
        self.time_layout=QVBoxLayout()
        self.timeWidget.setLayout(self.time_layout)
        self.timeButton = QPushButton('Show &Time Slider', self)
        self.timeButton.setEnabled(True)
        self.time_layout.addWidget(self.timeButton)

        #palette and field selection label
        self.pfWidget=QGroupBox('Palette and Field Selection')
        self.layout0.addWidget(self.pfWidget)

        #layout for renderer selection and palette/fieldname buttons
        self.pf_layout=QVBoxLayout()
        self.pfWidget.setLayout(self.pf_layout)
        #self.pfWidget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum)
        self.ren_layout = QHBoxLayout()
        self.pf_layout.addLayout( self.ren_layout )
    
        #renderer selection (for palette and fieldname)
        label = QLabel('Apply to...')
        self.sliceRadioButton = QRadioButton("Slice")
        self.volumeRadioButton = QRadioButton("Volume")
        if VisusCellConfigurationWidget.lastApplyTo=='volume' and self.viewerInstance.is3D():
            self.volumeRadioButton.setChecked(True)
        else:
            self.sliceRadioButton.setChecked(True)
        QObject.connect(self.sliceRadioButton, SIGNAL("clicked()"),self.applyToButtonTriggered)
        QObject.connect(self.volumeRadioButton,SIGNAL("clicked()"),self.applyToButtonTriggered)

        self.ren_layout.addWidget(label)
        self.ren_layout.addWidget(self.sliceRadioButton)
        self.ren_layout.addWidget(self.volumeRadioButton)

        #buttons to open palette and field selection
        self.paletteButton = QPushButton('&Palette', self)
        self.paletteButton.setEnabled(True)
        self.fieldButton = QPushButton('Select &Fields', self)
        self.fieldButton.setEnabled(True)

        self.pf_layout.addWidget(self.fieldButton)
        self.pf_layout.addWidget(self.paletteButton)

        QObject.connect(self.paletteButton,SIGNAL("clicked()"),self.paletteButtonTriggered)
        QObject.connect(self.timeButton,SIGNAL("clicked()"),self.timeButtonTriggered)
        QObject.connect(self.fieldButton,SIGNAL("clicked()"),self.fieldButtonTriggered)

        if VisusShowAdvanced:
            self.debugWidget=QGroupBox('Advanced')
            #self.debugWidget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum)
            self.debug_layout=QVBoxLayout()
            self.debugWidget.setLayout(self.debug_layout)
            self.layout0.addWidget(self.debugWidget)

            self.refreshButton = QPushButton('Force &Refresh', self)
            self.refreshButton.setEnabled(True)
            self.debug_layout.addWidget(self.refreshButton)
            QObject.connect(self.refreshButton,SIGNAL("clicked()"),self.viewerInstance.forceRefresh)

            self.treeviewButton = QPushButton('&Treeview', self)
            self.treeviewButton.setEnabled(True)
            self.debug_layout.addWidget(self.treeviewButton)
            QObject.connect(self.treeviewButton,SIGNAL("clicked()"),self.treeviewTriggered)

            self.logButton = QPushButton('&Log', self)
            self.logButton.setEnabled(True)
            self.debug_layout.addWidget(self.logButton)
            QObject.connect(self.logButton,SIGNAL("clicked()"),self.logTriggered)

            self.dataflowButton = QPushButton('&Dataflow', self)
            self.dataflowButton.setEnabled(True)
            self.debug_layout.addWidget(self.dataflowButton)
            QObject.connect(self.dataflowButton,SIGNAL("clicked()"),self.dataflowTriggered)

    def getSelectedRenderType(self):
        if self.sliceRadioButton.isChecked():
            return 'slice'
        return 'volume'

    def treeviewTriggered(self):
        self.viewerInstance.showTreeview(self.controller.current_cell_coords)

    def dataflowTriggered(self):
        self.viewerInstance.showDataflow(self.controller.current_cell_coords)

    def logTriggered(self):
        self.viewerInstance.showLog(self.controller.current_cell_coords)

    lastApplyTo='slice'
    def applyToButtonTriggered(self):
        if self.sliceRadioButton.isChecked():
            VisusCellConfigurationWidget.lastApplyTo='slice'
        else:
            VisusCellConfigurationWidget.lastApplyTo='volume'

    def timeButtonTriggered(self):
        self.viewerInstance.showTimeSlider(self.controller.current_cell_coords)

    def paletteButtonTriggered(self):
        self.viewerInstance.showPalette(self.getSelectedRenderType(),self.controller.current_cell_coords)

    def fieldButtonTriggered(self):
        self.viewerInstance.showFieldname(self.getSelectedRenderType(),self.controller.current_cell_coords)

    def setDefaults(self):
        pass

    def updateController(self, controller=None):
        pass

    def okTriggered(self, checked = False):
        """ okTriggered(checked: bool) -> None
        Update vistrail controller (if neccesssary) then close the widget

        """
        self.updateVistrail()
        self.updateController(self.controller)
        self.emit(SIGNAL('doneConfigure()'))

    def startOver(self):
        self.setDefaults();
