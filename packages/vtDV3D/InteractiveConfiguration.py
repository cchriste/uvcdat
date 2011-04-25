'''
Created on Dec 15, 2010

@author: tpmaxwel
'''
import sys, threading
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from core.modules.module_configure import StandardModuleConfigurationWidget
from ModuleStore import ModuleStoreDatabase
from core.modules.vistrails_module import Module, ModuleError
from core.interpreter.default import get_default_interpreter as getDefaultInterpreter
from core.modules.basic_modules import Integer, Float, String, Boolean, Variant
from ColorMapManager import ColorMapManager 
from collections import OrderedDict
from vtUtilities import *
import cdms2

class QtWindowLeveler( QObject ):
    
    update_range_signal = SIGNAL('update_range')
    
    WindowRelative = 0
    BoundsRelative = 1
   
    def __init__( self, **args ):
        QObject.__init__( self )
        self.OriginalWindow           = 1.0
        self.OriginalLevel            = 0.5
        self.CurrentWindow            = 1.0
        self.CurrentLevel             = 0.5
        self.sensitivity              = float( args.get( 'sensitivity', 1.0 ) )
        self.algorithm                = self.WindowRelative if args.get( 'windowing', True ) else self.BoundsRelative
        self.scaling = 1.0        
        self.invert = False

    def setDataRange( self, data_range ):
        self.scaling = 0.5 * ( data_range[0] + data_range[1] )
        self.OriginalWindow = ( data_range[1] - data_range[0] ) / self.scaling
        self.OriginalLevel = 1.0
      
        if( abs( self.OriginalWindow ) < 0.001 ): self.OriginalWindow = -0.001 if ( self.OriginalWindow < 0.0 ) else  0.001
        if( abs( self.OriginalLevel  ) < 0.001 ): self.OriginalLevel  = -0.001 if ( self.OriginalLevel  < 0.0 ) else  0.001
        self.setWindowLevel( self.OriginalWindow, self.OriginalLevel )
    
    def addUpdateRangeObserver( self, observer ):   
        self.connect( self, self.update_range_signal, observer )

    def windowLevel( self, X, Y, window_size ):
        result = None
        if self.algorithm == self.WindowRelative:
              window = self.InitialWindow
              level = self.InitialLevel
                
              dx = self.sensitivity * ( X - self.StartWindowLevelPositionX ) / float( window_size[0] )
              dy = self.sensitivity * ( self.StartWindowLevelPositionY - Y ) / float( window_size[1] )
               
              if ( abs( window ) > 0.01 ):   dx = dx * window
              else:                          dx = (dx * -0.01) if ( window < 0 ) else (dx *  0.01)
        
              if ( abs( level  ) > 0.01 ):   dy = dy * level
              else:                          dy = (dy * -0.01) if ( window < 0 ) else (dy *  0.01)
                
              if ( window < 0.0 ):           dx = -1 * dx
              if ( level < 0.0 ):            dy = -1 * dy
             
              newWindow = dx + window
              newLevel = level - dy
            
              if ( abs( newWindow ) < 0.01 ):  newWindow = -0.01 if( newWindow < 0 ) else  0.01 
              if ( abs( newLevel ) < 0.01 ):   newLevel  = -0.01 if( newLevel  < 0 ) else  0.01 
              
              if (( (newWindow < 0) and (self.CurrentWindow > 0 )) or ( (newWindow > 0) and (self.CurrentWindow < 0) )):
                  self.invert = not self.invert
            
              rmin = newLevel - 0.5*abs( newWindow )
              rmax = rmin + abs( newWindow )
              result = [ rmin*self.scaling, rmax*self.scaling, 1 if self.invert else 0 ]
              self.emit( self.update_range_signal, result )
            
              self.CurrentWindow = newWindow
              self.CurrentLevel = newLevel
        elif self.algorithm == self.BoundsRelative:
              dx =  self.sensitivity * ( X - self.StartWindowLevelPositionX ) 
              dy =  self.sensitivity * ( Y - self.StartWindowLevelPositionY ) 
              rmin = self.InitialRange[0] + ( dx / window_size[0] ) * self.InitialWindow
              rmax = self.InitialRange[1] + ( dy / window_size[1] ) * self.InitialWindow
              if rmin > rmax:   result =  [ rmax, rmin, 1 ]
              else:             result =  [ rmin, rmax, 0 ]
              self.CurrentWindow = result[1] - result[0]
              self.CurrentLevel =  0.5 * ( result[0] + result[1] )
        print " --- Set Range: ( %f, %f ),   Initial Range = ( %f, %f ), P = ( %d, %d ) dP = ( %f, %f ) " % ( result[0], result[1], self.InitialRange[0], self.InitialRange[1], X, Y, dx, dy )      
        return result
      
    def startWindowLevel( self, X, Y ):   
        self.InitialWindow = self.CurrentWindow
        self.InitialLevel = self.CurrentLevel  
        self.StartWindowLevelPositionX = float(X)
        self.StartWindowLevelPositionY = float(Y)
        rmin = self.InitialLevel - 0.5 * abs( self.CurrentWindow )
        rmax = rmin + abs( self.CurrentWindow )
        self.InitialRange = [ rmin, rmax ] if ( rmax > rmin ) else [ rmax, rmin ]
        print " --- Initialize Range: ( %f, %f ), P = ( %d, %d ) WL = ( %f, %f ) " % ( self.InitialRange[0]*self.scaling, self.InitialRange[1]*self.scaling, X, Y, self.InitialWindow, self.InitialLevel )      

    def setWindowLevel( self, window,  level ):
        if ( (self.CurrentWindow == window) and (self.CurrentLevel == level) ): return
        
        if (( (window < 0) and (self.CurrentWindow > 0 )) or ( (window > 0) and (self.CurrentWindow < 0) )):
              self.invert = not self.invert
              
        self.CurrentWindow = window
        self.CurrentLevel = level
        
        rmin = self.CurrentLevel - 0.5 * abs( self.CurrentWindow )
        rmax = rmin + abs( self.CurrentWindow )
        result = [ rmin*self.scaling, rmax*self.scaling, 1 if self.invert else 0 ]
        self.emit( self.update_range_signal, result )

        return result

###############################################################################   

class OutputRecManager: 
    
    sep = ';,:|!'   
            
    def __init__( self, serializedData = None ): 
        self.outputRecs = {}
        if serializedData <> None:
            self.deserialize( serializedData )
            
    def deleteOutput( self, dsid, outputName ):
        orecMap =  self.outputRecs.get( dsid, None )
        if orecMap: del orecMap[outputName] 

    def addOutputRec( self, dsid, orec ): 
        orecMap =  self.outputRecs.setdefault( dsid, {} )
        orecMap[ orec.name ] = orec

    def getOutputRec( self, dsid, outputName ):
        orecMap =  self.outputRecs.get( dsid, None )
        return orecMap[ outputName ] if orecMap else None

    def getOutputRecNames( self, dsid  ): 
        orecMap =  self.outputRecs.get( dsid, None )
        return orecMap.keys() if orecMap else []

    def getOutputRecs( self, dsid ):
        orecMap =  self.outputRecs.get( dsid, None )
        return orecMap.values() if orecMap else []
        
    def deserialize( self, serializedData ): 
        self.outputRecs = {}      
        outputRecData = serializedData.split( OutputRecManager.sep[0] )
        for outputRecItem in outputRecData:
            if outputRecItem:
                outputFields = outputRecItem.split( OutputRecManager.sep[1] )
                if outputFields:
                    try:
                        dsid = outputFields[0]
                        port_data = outputFields[1]
                        port_data_fields = port_data.split( OutputRecManager.sep[2] )
                        name = port_data_fields[0]
                        ndim = int( port_data_fields[1] )
                        variables = outputFields[2].split( OutputRecManager.sep[2] ) 
                        if variables: 
                            varList = []
                            for varEntry in variables:
                                varRec = varEntry.split( OutputRecManager.sep[3] ) 
                                if len( varRec[0] ) > 0: varList.append( varRec )
                            orec = OutputRec( name, ndim=ndim, varList=varList ) 
                            self.addOutputRec( dsid, orec ) 
                    except Exception, err:
                        print "Error deserializing port[%s] data: %s " % ( name, str( err ) )
                        
                            
    def serialize( self ):        
        portData = []
        for oRecData in self.outputRecs.items():
            dsetId = oRecData[0]
            orecMap = oRecData[1]
            for oRec in orecMap.values():
                port_name = oRec.name
                port_table = oRec.varTable
                nVarDims = oRec.ndim
                portData.append( "%c%s%c" % ( OutputRecManager.sep[0], dsetId, OutputRecManager.sep[1] ) )
                if port_table <> None:
                    portData.append( "%s%c%d%c" % (  port_name, OutputRecManager.sep[2], nVarDims, OutputRecManager.sep[1] ) )
                    for iRow in range( port_table.rowCount() ):
                        varNameLabel = port_table.cellWidget( iRow, 0 )
                        varName = str( varNameLabel.text() )
                        portData.append( "%c%s" % (  OutputRecManager.sep[2], varName ) )
                elif oRec.varList <> None:
                   portData.append( "%s%c%d%c" % (  port_name, OutputRecManager.sep[2], nVarDims, OutputRecManager.sep[1]  ) )
                   for varRec in oRec.varList:
                        portData.append( "%c%s%c" % (  OutputRecManager.sep[2], varRec[0],  OutputRecManager.sep[3] ) )
                elif oRec.varCombo <> None:
                   portData.append( "%s%c%d%c" % ( port_name, OutputRecManager.sep[2], nVarDims, OutputRecManager.sep[1]  ) )
                   varName = oRec.getVariable()
                   portData.append( "%c%s%c" % (  OutputRecManager.sep[2], varName,  OutputRecManager.sep[3] ) )               
        serializedData = ''.join( portData )
        print " -- PortData: %s " % serializedData
        return serializedData
    
###############################################################################   
         
class OutputRec:
    
    def __init__(self, name, **args ): 
        self.name = name
        self.varCombo = args.get( "varCombo", None )
        self.varTable = args.get( "varTable", None )
        self.varList = args.get( "varList", None )
        self.varSelection = args.get( "varSelection", None )
        self.type = args.get( "type", None )
        self.ndim = args.get( "ndim", 3 )

    def getVarList(self):
        vlist = []
        for vrec in self.varList:
            vlist.append( str( getItem( vrec ) ) )
        return vlist
    
    def getVariable(self):
        return str( self.varCombo.currentText() )

###############################################################################   
      
class ConfigurableFunction( QObject ):
    
    def __init__( self, name, function_args, key, **args ):
        QObject.__init__(self)
        self.name = name
        self.type = 'generic'
        self.args = function_args
        self.kwargs = args
        self.key = key
        self.functionID = -1 
        self.isLayerDependent = args.get( 'layerDependent', False )
#        self.parameterInputEnabled = True                                      # Handlers executed at:
        self.initHandler = args.get( 'init', None )         #    end of compute()
        self.openHandler = args.get( 'open', None )         #    key press
        self.startHandler = args.get( 'start', None )       #    left click
        self.updateHandler = args.get( 'update', None )     #    mouse drag or menu option choice

    def applyParameter( self, module, **args ):
        pass

    def init( self, module ):
        self.moduleID = module.moduleID
        if ( self.initHandler != None ):
            self.initHandler( module, **self.kwargs ) 
            
#    def setParameterInputEnabled( self, isEnabled ):
#        self.parameterInputEnabled = isEnabled
            
    def getHelpText( self ):
        return "<tr>   <td>%s</td>  <td>%s</td> <td>%s</td> </tr>\n" % ( self.key, self.name, self.type )

    def open( self, state ):
        if ( self.openHandler != None ) and ( self.name == state ):
            self.openHandler( )
            
    def close(self):
        pass
            
    def activateWidget( self, iren ):
        pass
    
    def reset(self):
        pass
        
    def start( self, state, x, y ):
        if ( self.startHandler != None ) and ( self.name == state ):
            self.startHandler( x, y )

    def update( self, state, x, y, wsize ):
        if ( self.updateHandler != None ) and ( self.name == state ):
            return self.updateHandler( x, y, wsize )
        return None
    
    def getTextDisplay(self, **args ):
        return None
    
    def wrapData( self, data ):
        wrappedData = []
        argClasses = iter( self.args )
        for data_elem in data:
            arg_sig = argClasses.next()
            arg_class = arg_sig[0] if IsListType( arg_sig ) else arg_sig
            wd_val = arg_class()
            wd_val.setValue( data_elem )
            wrappedData.append( wd_val )
        return wrappedData

    def unwrapData( self, data ):
        unwrappedData = []
        for data_elem in data:
            uw_val = data_elem.getResult()
            wrappedData.append( uw_val )
        return wrappedData
            
################################################################################

class WindowLevelingConfigurableFunction( ConfigurableFunction ):
    
    def __init__( self, name, key, **args ):
        ConfigurableFunction.__init__( self, name, [ ( Float, 'min'), ( Float, 'max'), ( Integer, 'ctrl') ], key, **args  )
        self.type = 'leveling'
        self.windowLeveler = QtWindowLeveler()
        if( self.initHandler == None ): self.initHandler = self.initLeveling
        if( self.startHandler == None ): self.startHandler = self.startLeveling
        if( self.updateHandler == None ): self.updateHandler = self.updateLeveling
        self.setLevelDataHandler = args.get( 'setLevel', None )
        self.getLevelDataHandler = args.get( 'getLevel', None )
        self.isDataValue = args.get( 'isDataValue', True )
        self.defaultRange = args.get( 'initRange', [ 0.0, 1.0, 1 ] )

    def applyParameter( self, module, **args ):
        try:
            self.setLevelDataHandler( self.range )
        except:
            pass

    def initLeveling( self, module, **args ):
        self.module = module
        initial_range =  self.defaultRange if ( self.getLevelDataHandler == None ) else self.getLevelDataHandler()
        self.range = module.getInputValue( self.name, initial_range ) if not module.newDataset else initial_range
        self.setLevelDataHandler( self.range )
        self.windowLeveler.setDataRange( self.range )
        module.setParameter( self.name, self.range )
#        print "    ***** Init Leveling Parameter: %s, initial range = %s" % ( self.name, str(self.range) )
        
    def startLeveling( self, x, y ):
        self.windowLeveler.startWindowLevel( x, y )

    def getTextDisplay(self, **args ):
        rmin = self.range[0] # if not self.isDataValue else self.module.getDataValue( self.range[0] )
        rmax = self.range[1] # if not self.isDataValue else self.module.getDataValue( self.range[1] )
        units = 'X'
        return " Range: %.4G, %.4G %s." % ( rmin, rmax, units )
            
    def updateLeveling( self, x, y, wsize ):
        self.range = self.windowLeveler.windowLevel( x, y, wsize )
        self.setLevelDataHandler( self.range )
        self.module.render()
        return self.range # self.wrapData( range )

################################################################################

class GuiConfigurableFunction( ConfigurableFunction ):
    
    start_parameter_signal = SIGNAL('start_parameter')
    update_parameter_signal = SIGNAL('update_parameter')
    finalize_parameter_signal = SIGNAL('finalize_parameter')
    
    def __init__( self, name, guiClass, key, **args ):
        ConfigurableFunction.__init__( self, name, guiClass.getSignature(), key, **args  )
        self.type = 'gui'
        self.guiClass = guiClass
        if( self.initHandler == None ): self.initHandler = self.initGui
        if( self.openHandler == None ): self.openHandler = self.openGui
        self.setValueHandler = args.get( 'setValue', None )
        self.getValueHandler = args.get( 'getValue', None )
        self.startConfigurationObserver = args.get( 'start', None )
        self.updateConfigurationObserver = args.get( 'update', None )
        self.finalizeConfigurationObserver = args.get( 'finalize', None )
        self.gui = None
        
    def initGui( self, module, **args ):
        if self.gui == None: 
            self.gui = self.guiClass.getInstance( self.guiClass, self.name, module, **args  )
            if self.startConfigurationObserver <> None:
                self.gui.connect( self.gui, self.start_parameter_signal, self.startConfigurationObserver )
            if self.updateConfigurationObserver <> None:
                self.gui.connect( self.gui, self.update_parameter_signal, self.updateConfigurationObserver )
            if self.finalizeConfigurationObserver <> None:
                self.gui.connect( self.gui, self.finalize_parameter_signal, self.finalizeConfigurationObserver )
        initial_value = None if ( self.getValueHandler == None ) else self.getValueHandler()          
        value = module.getInputValue( self.name, initial_value )  # if self.parameterInputEnabled else initial_value
        if value <> None: 
            self.gui.setValue( value )
            self.setValue( value )
            module.setResult( self.name, value )

    def openGui( self ):
        if self.getValueHandler <> None:
             value = self.getValueHandler()  
             self.gui.initWidgetFields( value )
        self.gui.show()
        
    def getTextDisplay(self, **args ):
        return self.gui.getTextDisplay( **args )
       
    def setValue( self, value ):
        if self.setValueHandler <> None: 
            self.setValueHandler( value )

################################################################################

class WidgetConfigurableFunction( ConfigurableFunction ):
        
    def __init__( self, name, signature, widgetWrapper, key, **args ):
        ConfigurableFunction.__init__( self, name, signature, key, **args  )
        self.type = 'widget'
        self.widget = None
        self.widgetWrapper = widgetWrapper
        if( self.initHandler == None ): self.initHandler = self.initWidget
        if( self.openHandler == None ): self.openHandler = self.openWidget
        self.setValueHandler = args.get( 'setValue', None )
        self.getValueHandler = args.get( 'getValue', None )
        
    def initWidget( self, module, **args ):
        if self.widget == None: self.widget = self.widgetWrapper( self.name, module, **args )
        initial_value = None if ( self.getValueHandler == None ) else self.getValueHandler() 
        value = module.getInputValue( self.name, initial_value ) # if self.parameterInputEnabled else initial_range
        if value <> None: 
            self.widget.setInitialValue( value )         
            self.setValue( value )
            module.setParameter( self.name, value )
                
    def reset(self):
        self.widget.reset()
        
    def close(self):
        self.widget.close()

    def activateWidget( self, iren ):
        self.widget.activateWidget( iren )

    def openWidget( self ):
        start_value = None if ( self.getValueHandler == None ) else self.getValueHandler() 
        self.widget.open( start_value )
        
    def getTextDisplay(self, **args ):
        return self.widget.getTextDisplay(**args)

    def setValue( self, value ):
        if self.setValueHandler <> None: 
            self.setValueHandler( value )
       
    def getValue( self ):
        if self.getValueHandler <> None: 
            return self.getValueHandler()
            
################################################################################

class ModuleDocumentationDialog( QDialog ):
    """
    ModuleDocumentationDialog is a dialog for showing module documentation.  It has a set of tabbed pages corresponding to a set of topics.

    """
    def __init__(self, useHTML=True, parent=None):
        QDialog.__init__(self, parent)
        self.textPages = {}
        self.useHTML = useHTML
        self.setWindowTitle('Module Documentation')
        self.setLayout(QVBoxLayout())
        self.layout().addStrut(600)
        self.closeButton = QPushButton('Ok', self)
        self.tabbedWidget = QTabWidget()
        self.layout().addWidget( self.tabbedWidget )         
        self.layout().addWidget(self.closeButton)
        self.connect(self.closeButton, SIGNAL('clicked(bool)'), self.close)
        self.closeButton.setShortcut('Enter')
        
    def addCloseObserver( self, observer ):
        self.connect(self.closeButton, SIGNAL('clicked(bool)'), observer )
    
    def getTabPage( self, name ): 
        tabPage = self.textPages.get( name, None ) 
        if tabPage == None:  
            textEdit = QTextEdit(self)
            textEdit.setReadOnly(True)
            index = self.tabbedWidget.addTab( textEdit, name ) 
            tabPage = [ textEdit, [] ]
            self.textPages[name] = tabPage
        return tabPage
    
    def clearTopic( self, topic ):
        tabPage = self.textPages.get( topic, None )
        if tabPage <> None: tabPage[1] = []
                                    
    def addDocument( self, topic, text ):
        tabPage = self.getTabPage( topic )
        tabPage[1].append( text )
        
    def generateDisplayedText(self):
        for tabPage in self.textPages.values():
            if self.useHTML:    tabPage[0].setHtml ( '\n<hr width="90%" color="#6699ff" size="6" />\n'.join( tabPage[1] ) )               
            else:               tabPage[0].setText ( '\n############################################################\n'.join( tabPage[1] ) )
        
    def clearDocuments(self):
        for tabPage in self.textPages.values():
            tabPage[1] = []
        
    def show(self):
        self.generateDisplayedText()
        QDialog.show(self)
        
#        self.textEdit.setTextCursor( QTextCursor(self.textEdit.document()) )   
        
 ################################################################################
 
class IVModuleConfigurationDialog( QWidget ):
    """
    IVModuleConfigurationDialog ...   
    """ 
    instances = {}
    activeModuleList = []
         
    def __init__(self, name, **args ):
        QWidget.__init__(self, None)
        self.modules = OrderedDict()
        self.module = None
        self.name = name
        title = ( '%s configuration' % name )
        self.setWindowTitle( title )        
        self.setLayout(QVBoxLayout())
        self.tabbedWidget = QTabWidget()
        self.layout().addWidget( self.tabbedWidget ) 
        self.layout().setMargin(5)
        self.layout().setSpacing(5)
        self.createContent()
        self.createButtonLayout()
        self.createActiveModulePanel()
    
    @staticmethod    
    def getInstance( klass, name, caller, **args  ):
#        stack = inspect.stack()
#        frame = stack[0][0]
#        print " ---> %s: %s" % ( frame.__class__, dir( frame ) )
        instance = IVModuleConfigurationDialog.instances.setdefault( name, klass( name, **args )  )
        instance.addActiveModule( caller )
        return instance 
                              
    def createContent(self ):
        """ createContent() 
        Creates the content of this widget       
        """
        pass
    
    def addActiveModule( self, module ):
        if not module in self.modules:
            row = len( self.modules )
            activateCheckBox = QCheckBox( 'Activate' )
            activateCheckBox.setChecked( True )
            module_label = QLabel( module.getName()  )
            self.moduleTabLayout.addWidget( module_label, row, 0 )
            self.moduleTabLayout.addWidget( activateCheckBox, row, 1 )
            if not module in self.modules:
                if not ( self.activeModuleList and self.activeModuleList[-1] == module ):
                    self.activeModuleList.append( module )
                    self.connect( self, self.update_animation_signal, module.updateAnimation )
            self.modules[ module ] = activateCheckBox
            self.connect( activateCheckBox, SIGNAL( "stateChanged(int)" ), callbackWrapper( module.setActivation, self.name ) )  
            self.moduleTabLayout.update()
#            self.registerModule( module )
#            print "Add active module %s to dialog %s[%s], modules: %s" % ( module.getName(), self.name, str(id(self)), str(self.modules.keys() ) )
         
    def parameterUpdating(self):
        for module in self.modules:
            if self.modules[ module ].isChecked():
                if module.parameterUpdating( self.name ):
                    return True
        return False

    def updateConfiguration(self):
        for module in self.modules:
            if self.modules[ module ].isChecked() :
                module.updateConfigurationObserver( self.name, self.getValue() )        

    def initiateParameterUpdate(self):
        for module in self.modules:
            if self.modules[ module ].isChecked() :
                module.initiateParameterUpdate( self.name )
 
    def refreshPipeline(self):
        wmods = getWorkflowObjectMap()
        for module in self.modules:   
            wmod = wmods[ module.moduleID ]
            if wmod == None:
                executeWorkflow()
                return
        
    def getTextDisplay( self, **args  ):
        value = self.getValue()
        return "%s: %s" % ( self.name, self.getTextValue( value ) )
       
    def getTextValue( self, value, **args ):
        text_value = None
        text_value_priority = 0
        for module in self.modules:
            if self.modules[ module ].isChecked() :
                tval, priority = module.getParameterDisplay( self.name, value )
                if tval and ( priority > text_value_priority ): 
                    text_value = tval
                    text_value_priority = priority
        return str( text_value )
 
    def activateWidget( self, iren ):
        pass

    def initWidgetFields( self, value ):
        pass

    def createActiveModulePanel(self ):
        """ createEditor() -> None
        Configure sections       
        """       
        activeModuleTab = QWidget()        
        self.tabbedWidget.addTab( activeModuleTab, 'Active Modules' )
        self.moduleTabLayout = QGridLayout()
        self.moduleTabLayout.setMargin( 5 )
        self.moduleTabLayout.setSpacing( 5 )
        activeModuleTab.setLayout( self.moduleTabLayout )
                      
#QLayout.removeItem (self, QLayoutItem)
#QLayout.count (self)
#QLayoutItem QLayout.itemAt (self, int index)
#QLayout.addItem (self, QLayoutItem)

#    def refreshActiveModules(self): 
#        layout = QGridLayout()
#        self.activeModuleTab.setLayout( layout ) 
#        layout.setMargin(10)
#        layout.setSpacing(20)
#        moduleIter = iter( self.modules )     
#        for iRow in range( len( self.modules ) ):
#            module = moduleIter.next()            
#            activateCheckBox = QCheckBox('Activate')
#            activateCheckBox.setChecked( self.modules[module] )
#            module_label = QLabel( module.getName()  )
#            layout.addWidget( module_label, iRow, 0 )
#            layout.addWidget( activateCheckBox, iRow, 1 )
#            self.connect( activateCheckBox, SIGNAL("stateChanged(int)"), self.updateActiveModules )  
#
#    def updateActiveModules( self, val ):
#        for item in self.modules.items():
#            active = item[1]
#            module = item[0]

    def createButtonLayout(self):
        """ createButtonLayout() -> None
        Construct Ok & Cancel button
        
        """
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setMargin(5)
        self.okButton = QPushButton('&OK', self)
        self.okButton.setAutoDefault(False)
        self.okButton.setFixedWidth(100)
        self.buttonLayout.addWidget(self.okButton)
        self.cancelButton = QPushButton('&Cancel', self)
        self.cancelButton.setAutoDefault(False)
        self.cancelButton.setShortcut('Esc')
        self.cancelButton.setFixedWidth(100)
        self.buttonLayout.addWidget(self.cancelButton)
        self.layout().addLayout(self.buttonLayout)
        self.connect(self.okButton, SIGNAL('clicked(bool)'), self.okTriggered)
        self.connect(self.cancelButton, SIGNAL('clicked(bool)'), self.close)
                    
    def okTriggered(self, checked = False):
        """ okTriggered(checked: bool) -> None
        Update vistrail controller (if neccesssary) then close the widget        
        """
        self.finalizeParameter()
        self.close()

    def closeTriggered(self, checked = False):
        self.close()

    def finalizeParameter( self, *args ):
        self.emit( GuiConfigurableFunction.finalize_parameter_signal, self.name, self.getValue() )

    def startParameter( self, *args ):
        self.emit( GuiConfigurableFunction.start_parameter_signal, self.name, self.getValue() )

    def updateParameter( self, *args ):
        self.emit( GuiConfigurableFunction.update_parameter_signal, self.name, self.getValue() )

    @staticmethod   
    def getSignature( self ):
        return []
        
    def getValue( self ):
        return None

    def setValue( self, value ):
        pass

################################################################################
 
class IVModuleWidgetWrapper( QObject ):
    """
    IVModuleConfigurationDialog ...   
    """ 
       
    def __init__(self, name, module, **args ):
        QObject.__init__(self)
        self.name = name
        self.module = module
        self.initial_value = None
        self.current_value = None
#        self.configToParameterConversion = args.pop( 'configToParameter' )
#        self.parameterToConfigConversion = args.pop( 'parameterToConfig' )
        self.createContent( )
                              
    def createContent( self ):
        """ createContent() 
        Creates the content of this widget       
        """
        pass
    
    def getTextDisplay( self ):
        return "%s: %s" % ( self.name, str(self.getCurrentValue() ) )
 
    def activateWidget( self, iren ):
        pass
    
    def render(self):
        self.module.render()
           
    def close():
        pass 

    def open( start_value ):
        pass 
    
    def finalizeParameter( self, *args ):
        self.module.finalizeConfigurationObserver( self.name, *args )

    def startParameter( self, *args ):
        self.module.startConfigurationObserver( self.name, *args )

    def updateParameter( self, *args ):
        param_value = self.getValue()
        self.module.updateConfigurationObserver( self.name, param_value, *args )
        
    def getWidgetConfiguration( self ):
        return None
    
    def setInitialValue( self,  initial_value ):
        self.initial_value =  initial_value
        
    def getValue(self):
        self.current_value = self.getWidgetConfiguration() 
#        self.current_value = self.configToParameterConversion( config_value )
        return self.current_value

    def getCurrentValue(self):
        return self.current_value
        
    def reset(self):
        if self.initial_value <> None:
            self.setValue( self.initial_value ) 
            
    def setValue( self, parameter_value ):
        config_value = parameter_value # self.parameterToConfigConversion( parameter_value )
        self.setWidgetConfiguration( config_value )
        return config_value

    def setWidgetConfiguration( self, value ):
        pass

################################################################################
        
class ColormapConfigurationDialog( IVModuleConfigurationDialog ):
    """
    ColormapConfigurationDialog ...   
    """ 
       
    def __init__(self, name, **args ):
        IVModuleConfigurationDialog.__init__( self, name, **args )
        
    @staticmethod   
    def getSignature():
        return [ (String, 'name'), ( Integer, 'invert'), ]
        
    def getValue(self):
        checkState = 1 if ( self.invertCheckBox.checkState() == Qt.Checked ) else 0
        return [ str( self.colormapCombo.currentText() ), checkState ]

    def setValue( self, value ):
        colormap_name = str( value[0] )
        check_state = Qt.Checked if value[1] else Qt.Unchecked
        itemIndex = self.colormapCombo.findText( colormap_name, Qt.MatchFixedString )
        if itemIndex >= 0: self.colormapCombo.setCurrentIndex( itemIndex )
        else: print>>sys.stderr, " Can't find colormap: %s " % colormap_name
        self.invertCheckBox.setCheckState( check_state )
        
    def createContent(self ):
        """ createEditor() -> None
        Configure sections       
        """       
        colorMapTab = QWidget() 
        self.tabbedWidget.addTab( colorMapTab, 'Colormap' )                      
        layout = QGridLayout()
        colorMapTab.setLayout( layout ) 
        layout.setMargin(10)
        layout.setSpacing(20)
       
        colormap_label = QLabel( "Colormap:"  )
        layout.addWidget( colormap_label, 0, 0 ) 

        self.colormapCombo =  QComboBox ( self.parent() )
        colormap_label.setBuddy( self.colormapCombo )
        self.colormapCombo.setMaximumHeight( 30 )
        layout.addWidget( self.colormapCombo, 0,1 )
        for cmap in ColorMapManager.getColormaps(): self.colormapCombo.addItem( cmap )   
        self.connect( self.colormapCombo, SIGNAL("currentIndexChanged(QString)"), self.updateParameter )  
        
        self.invertCheckBox = QCheckBox('Invert')
        layout.addWidget( self.invertCheckBox, 1, 0, 1, 2 )
        self.connect( self.invertCheckBox, SIGNAL("stateChanged(int)"), self.updateParameter )  

################################################################################
        
class LayerConfigurationDialog( IVModuleConfigurationDialog ):
    """
    LayerConfigurationDialog ...   
    """ 
       
    def __init__(self, name, **args ):
        IVModuleConfigurationDialog.__init__( self, name, **args )
        
    @staticmethod   
    def getSignature():
        return [ (String, 'layer'), ]
        
    def getValue(self):
        return [ str( self.layerCombo.currentText() ), ]

    def setValue( self, value ):
        if value:
            layer_name = str( value[0] )
            itemIndex = self.layerCombo.findText( layer_name, Qt.MatchFixedString )
            if itemIndex >= 0: self.layerCombo.setCurrentIndex( itemIndex )
            else: print>>sys.stderr, " Can't find colormap: %s " % layer_name

    def queryLayerList( self, ndims=3 ):
        portName = 'volume' if ( ndims == 3 ) else 'slice'
        mid = self.module.id
        while mid <> None:
            mid, mport = getConnectedModuleId( self.controller, mid, portName ) 
            if mid:
                module = self.controller.current_pipeline.modules[ mid ]
                dsetId = module.getAnnotation( "datasetId" )
                if dsetId:
                    portData = getFunctionParmStrValues( module, "portData" )
                    if portData:
                        serializedPortData = portData[0]
                        oRecMgr = OutputRecManager( serializedPortData )
                        orec = oRecMgr.getOutputRec( dsetId, portName )
                        return orec.getVarList()
        return []      
            
    def getLayerList( self ):
        for module in self.modules:
            layerList = module.getLayerList()
            if len(layerList): return layerList
        return []

    def initWidgetFields( self, value ):
        self.layerCombo.clear()
        layerlist = self.getLayerList()
        for layer in layerlist:
            if layer: self.layerCombo.addItem( layer ) 
                
    def createContent(self ):
        """ createEditor() -> None
        Configure sections       
        """       
        colorMapTab = QWidget() 
        self.tabbedWidget.addTab( colorMapTab, 'Layers' )                      
        layout = QGridLayout()
        colorMapTab.setLayout( layout ) 
        layout.setMargin(10)
        layout.setSpacing(20)
       
        layer_label = QLabel( "Layer:"  )
        layout.addWidget( layer_label, 0, 0 ) 

        self.layerCombo =  QComboBox ( self.parent() )
        layer_label.setBuddy( self.layerCombo )
        self.layerCombo.setMaximumHeight( 30 )
        layout.addWidget( self.layerCombo, 0, 1 ) 
        self.connect( self.layerCombo, SIGNAL("currentIndexChanged(QString)"), self.updateParameter )  
        


class DV3DConfigurationWidget(StandardModuleConfigurationWidget):

    def __init__(self, module, controller, title, parent=None):
        """ DV3DConfigurationWidget(module: Module,
                                       controller: VistrailController,
                                       parent: QWidget)
                                       -> LayerConfigurationWidget
        Setup the dialog ...
        
        """
        StandardModuleConfigurationWidget.__init__(self, module, controller, parent)
        self.setWindowTitle( title )
        self.moduleId = module.id
        self.pmod = self.module_descriptor.module.forceGetPersistentModule( module.id )
        self.getParameters( module )
        self.createLayout()

    def getParameters( self, module ):
        pass

    def createLayout( self ):
        pass

    def createButtonLayout(self):
        """ createButtonLayout() -> None
        Construct Ok & Cancel button
        
        """
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setMargin(5)
        self.okButton = QPushButton('&OK', self)
        self.okButton.setAutoDefault(False)
        self.okButton.setFixedWidth(100)
        self.buttonLayout.addWidget(self.okButton)
        self.cancelButton = QPushButton('&Cancel', self)
        self.cancelButton.setAutoDefault(False)
        self.cancelButton.setShortcut('Esc')
        self.cancelButton.setFixedWidth(100)
        self.buttonLayout.addWidget(self.cancelButton)
        self.layout().addLayout(self.buttonLayout)
        self.connect(self.okButton, SIGNAL('clicked(bool)'), self.okTriggered)
        self.connect(self.cancelButton, SIGNAL('clicked(bool)'), self.close)
        
    def okTriggered(self):
        pass
       
    @staticmethod
    def readVariableList( cdmsFile ):
        dataset = cdms2.open( cdmsFile ) 
        vList = [ ] 
        if dataset:
            for var in dataset.variables:
                vardata = dataset[var]
                var_ndim = getVarNDim( vardata )
                vList.append( ( var, var_ndim ) ) 
            dataset.close()  
        return vList        

    @staticmethod
    def getTimeRange( mid ): 
        import api
        controller = api.get_current_controller()
        moduleId = mid
        datasetId = None
        timeRange = None
        while moduleId:
            moduleId, portName = getConnectedModuleId( controller, moduleId, 'dataset', True )
            if moduleId <> None:
                module = controller.current_pipeline.modules[ moduleId ]
                datasetIdInput = getFunctionParmStrValues( module, "datasetId" )
                if datasetIdInput: 
                    datasetId = getItem( datasetIdInput )
                    datasetsInput = getFunctionParmStrValues( module, "datasets" )
                    if datasetsInput: 
                        timeRangeInput = getFunctionParmStrValues( module, "timeRange" )
                        if timeRangeInput: timeRange = [ int(timeRangeInput[0]), int(timeRangeInput[1]) ]
                        moduleId = None
        return ( datasetId, timeRange )

    @staticmethod
    def getVariableList( mid ): 
        import api
        controller = api.get_current_controller()
        moduleId = mid
        cdmsFile = None
        datasetId = None
        timeRange = None
        variableList = [ ]
        while moduleId <> None:
            moduleId, portName = getConnectedModuleId( controller, moduleId, 'dataset', True )
            if moduleId <> None:
                module = controller.current_pipeline.modules[ moduleId ]
                datasetIdInput = getFunctionParmStrValues( module, "datasetId" )
                if datasetIdInput: 
                    datasetId = getItem( datasetIdInput )
                    datasetsInput = getFunctionParmStrValues( module, "datasets" )
                    if datasetsInput: 
                        datasets = deserializeStrMap( getItem( datasetsInput ) )
                        cdmsFile = datasets[ datasetId ]
                        vlist = DV3DConfigurationWidget.readVariableList( cdmsFile )
                        variableList.extend( vlist )
                        timeRangeInput = getFunctionParmStrValues( module, "timeRange" )
                        if timeRangeInput: timeRange = [ int(timeRangeInput[0]), int(timeRangeInput[1]) ]
                        moduleId = None
        moduleId = mid
        while moduleId <> None:
            moduleId, portName = getConnectedModuleId( controller, moduleId, 'dataset', True )
            if moduleId <> None:
                module = controller.current_pipeline.modules[ moduleId ]
                taskInput = getFunctionParmStrValues( module, "task" )
                if taskInput:
                    taskMapInput = decodeFromString( getItem( taskInput ) ) 
                    if taskMapInput:
                        taskMap = taskMapInput       
                        taskRecord = taskMap.get( datasetId, None )
                        if taskRecord:
                            outputs = taskRecord[2].split(';')
                            for output in outputs:
                                outputData = output.split(',')
                                if len(outputData) > 1:
                                    variableList.append( ( outputData[1], int( outputData[2] ) ) )
                    moduleId = None
        return ( variableList, datasetId, cdmsFile, timeRange )


    def persistParameter( self, parameter_name, output, **args ):
        self.pmod.persistParameter( parameter_name, output, **args )
        self.pmod.persistVersionMap() 
                
    def queryLayerList( self, ndims=3 ):
        portName = 'volume' if ( ndims == 3 ) else 'slice'
        mid = self.module.id
        while mid <> None:
            mid, mport = getConnectedModuleId( self.controller, mid, portName ) 
            if mid:
                module = self.controller.current_pipeline.modules[ mid ]
                dsetIdData = getFunctionParmStrValues( module, "datasetId" )
                if dsetIdData:
                    dsetId = dsetIdData[0]
                    portData = getFunctionParmStrValues( module, "portData" )
                    if portData:
                        serializedPortData = portData[0]
                        oRecMgr = OutputRecManager( serializedPortData )
                        orec = oRecMgr.getOutputRec( dsetId, portName )
                        return orec.getVarList()
        return []        

################################################################################
        
class AnimationConfigurationDialog( IVModuleConfigurationDialog ):
    """
    AnimationConfigurationDialog ...   
    """ 
    update_animation_signal = SIGNAL('update_animation')      
   
    def __init__(self, name, **args):
        self.iTimeStep = 0
        self.maxSpeedIndex = 100
        ss = args.get( "speedScale", 1.0 )
        self.delayTimeScale = (2.0*ss)/self.maxSpeedIndex
        self.running = False
        self.timeRange = None
        self.datasetId = None
        self.timer = QTimer()
        self.timer.connect( self.timer, SIGNAL('timeout()'), self.animate )
        IVModuleConfigurationDialog.__init__( self, name, **args )
                                  
    @staticmethod   
    def getSignature():
        return [ ( Integer, 'timeStep'), ]
        
    def getValue(self):
        return [ self.iTimeStep ]

    def setValue( self, value ):
        iTS = getItem( value )
        if self.timeRange and ( ( iTS > self.timeRange[1] ) or  ( iTS < self.timeRange[0] ) ): iTS = self.timeRange[0]
        self.iTimeStep = iTS
                
    def loadAnimation(self):
        self.getTimeRange(  )
        for iTS in range( self.timeRange[0], self.timeRange[1] ):
            self.setTimestep( iTS ) 
            time.sleep( 0.01 ) 
            if not self.running: break
                
    def step( self ):
        if not self.running:
            self.setTimestep( self.iTimeStep + 1 )

    def reset( self ):
        if self.running:
            self.runButton.setText('Run')
            self.running = False
        self.setTimestep(0)

    def getTimeRange( self ): 
#        wmods = getWorkflowObjectMap()
        for module in self.modules: 
            timeRangeInput =  module.getInputValue( "timeRange", None )
            if timeRangeInput: 
                self.timeRange = [ int(timeRangeInput[0]), int(timeRangeInput[1]) ]
                return
            
                          
#            wmod = wmods[ module.moduleID ]
#            if wmod:
#                try:
#                    timeRangeInput =  wmod.forceGetInputFromPort( "timeRange", None )
#                    if timeRangeInput: 
#                        self.timeRange = [ int(timeRangeInput[0]), int(timeRangeInput[1]) ]
#                        return
#                except: pass

    def setTimestep1( self, iTimestep ):
        self.setValue( iTimestep )
        self.emit( self.update_animation_signal, self.iTimeStep, self.getTextDisplay() )

    def setTimestep( self, iTimestep ):
        self.setValue( iTimestep )
        print " ** Update Animation, timestep = %d " % self.iTimeStep  
        for module in self.activeModuleList:
            dvLog( module, " ** Update Animation, timestep = %d " % ( self.iTimeStep ) )
            try:
                module.updateAnimation( self.iTimeStep, self.getTextDisplay() )
            except Exception, err:
                dvLog( module, " ----> Error %s " % str( err ) )
       
    def setTimestep1(self, iTimestep, refresh = True ):
        if refresh: 
            self.refreshPipeline()
            self.getTimeRange()
        self.setValue( iTimestep )
        self.updateParameter()

    def stop(self):
        self.runButton.setText('Run')
        self.running = False
        self.timer.stop()       

    def start(self):
        self.getTimeRange()
        self.runButton.setText('Stop')
        self.running = True
        self.timer.start()       
        
    def run( self ): 
        if self.running: self.stop()           
        else: self.start()
        
#            self.runButton.setText('Stop')
#            executeWorkflow()
#            self.getTimeRange()
#            if inGuiThread:
#                self.animate()
#            else:
#            self.running = True
#            self.loadAnimation()
#            self.getTimeRange()
#            self.runButton.setDisabled(True)
#            self.setValue( 0 )
#            self.timer.start()
#            self.runThread = threading.Thread( target=self.animate )
#            self.runThread.start()
             
    def animate(self):
        self.setTimestep( self.iTimeStep + 1 )   
        delayTime = ( self.maxSpeedIndex - self.speedSlider.value() + 1 ) * self.delayTimeScale 
        time.sleep( delayTime ) 
                
    def run1(self):
        if self.running:
            self.runButton.setText('Run')
            self.running = False
        else:
            self.runButton.setText('Stop')
            executeWorkflow()
            self.running = True
            self.runThread = threading.Thread( target=self.animate )
            self.runThread.start()
     
        
    def animate1(self):
        refresh = True
        while self.running:
            self.initiateParameterUpdate()
            self.setTimestep( self.iTimeStep + 1, refresh )
            while self.parameterUpdating():
                time.sleep(0.01)
            delayTime =  ( self.maxSpeedIndex - self.speedSlider.value() + 1 ) * self.delayTimeScale    
            time.sleep( delayTime ) 
            refresh = False
#            printTime( 'Finish Animation delay' )
                
#    def setDelay( self, dval  ):
#        dval = 
#        self.delay = delay_in_sec if ( delay_in_sec<>None ) else self.speedSlider.value()/100.0
        
        
    def createContent(self ):
        """ createEditor() -> None
        Configure sections       
        """       
        animMapTab = QWidget()        
        self.tabbedWidget.addTab( animMapTab, 'Animation' )                                       
        layout = QVBoxLayout()
        animMapTab.setLayout( layout ) 
        layout.setMargin(10)
        layout.setSpacing(20)
       
        label_layout = QHBoxLayout()
        label_layout.setMargin(5)
        anim_label = QLabel( "Speed:"  )
        label_layout.addWidget( anim_label  ) 
        self.speedSlider = QSlider( Qt.Horizontal )
        self.speedSlider.setRange( 0, self.maxSpeedIndex )
        self.speedSlider.setSliderPosition( self.maxSpeedIndex )
#        self.connect(self.speedSlider, SIGNAL('valueChanged()'), self.setDelay )
        anim_label.setBuddy( self.speedSlider )
        label_layout.addWidget( self.speedSlider  ) 
        
        layout.addLayout( label_layout )
        
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setMargin(5)
        layout.addLayout(self.buttonLayout)
        
        self.runButton = QPushButton( 'Run', self )
        self.runButton.setAutoDefault(False)
        self.runButton.setFixedWidth(100)
        self.buttonLayout.addWidget(self.runButton)
        self.connect(self.runButton, SIGNAL('clicked(bool)'), self.run )

        self.stepButton = QPushButton( 'Step', self )
        self.stepButton.setAutoDefault(False)
        self.stepButton.setFixedWidth(100)
        self.buttonLayout.addWidget(self.stepButton)
        self.connect(self.stepButton, SIGNAL('clicked(bool)'), self.step )

        self.resetButton = QPushButton( 'Reset', self )
        self.resetButton.setAutoDefault(False)
        self.resetButton.setFixedWidth(100)
        self.buttonLayout.addWidget(self.resetButton)
        self.connect(self.resetButton, SIGNAL('clicked(bool)'), self.reset )

#class LayerConfigurationDialog( IVModuleConfigurationDialog ):
#    """
#    LayerConfigurationDialog ...   
#    """    
#    def __init__(self, name, **args):
#        self.activeLayer = False
#        IVModuleConfigurationDialog.__init__( self, name, **args )
#                
#    @staticmethod   
#    def getSignature():
#        return [ ( String, 'layer'), ]
#        
#    def getValue(self):
#        return [ self.activeLayer ]
#
#    def setValue( self, value ):
#        self.activeLayer = getItem( value ) 
#        
#    def createContent(self ):
#        """ createEditor() -> None
#        Configure sections       
#        """       
#        layerTab = QWidget()        
#        self.tabbedWidget.addTab( layerTab, 'Layers' )                                       
#        layersLayout = QVBoxLayout()
#        layerTab.setLayout( layersLayout ) 
#        layersLayout.setMargin(10)
#        layersLayout.setSpacing(20)
#                               
#        layer_selection_Layout = QHBoxLayout()      
#        layer_selection_label = QLabel( "Select Layer:"  )
#        layer_selection_Layout.addWidget( layer_selection_label ) 
#        self.layersCombo =  QComboBox ( self )
#        layer_selection_label.setBuddy( self.layersCombo )
##        layersCombo.setMaximumHeight( 30 )
#        layer_selection_Layout.addWidget( self.layersCombo ) 
#        
#        for layer in self.layerList:               
#            self.layersCombo.addItem( str(layer) ) 
#        
#        if self.layer:
#            currentLayerIndex = self.layersCombo.findText ( self.layer )   
#            if currentLayerIndex >= 0: self.layersCombo.setCurrentIndex( currentLayerIndex ) 
# 
#        layersLayout.addLayout( layer_selection_Layout )

                
class LayerConfigurationWidget(DV3DConfigurationWidget):
    """
    LayerConfigurationWidget ...
    
    """
    def __init__(self, module, controller, parent=None):
        """ LayerConfigurationWidget(module: Module,
                                       controller: VistrailController,
                                       parent: QWidget)
                                       -> LayerConfigurationWidget
        Setup the dialog ...
        
        """
        self.layer = None
        DV3DConfigurationWidget.__init__(self, module, controller, 'Layer Configuration', parent) 
        
    def getParameters( self, module ):
        self.layerList = self.queryLayerList()
        layerData = getFunctionParmStrValues( module, "layer" )
        if layerData: self.layer = layerData[0]
                               
    def createLayout(self):
        """ createEditor() -> None
        Configure sections
        
        """
        self.setLayout( QVBoxLayout() )
        self.layout().setMargin(10)
        self.layout().setSpacing(10)

        self.tabbedWidget = QTabWidget()
        self.layout().addWidget( self.tabbedWidget ) 

        self.createButtonLayout() 

        layersTab = QWidget()        
        self.tabbedWidget.addTab( layersTab, 'Layers' ) 
        layersLayout = QVBoxLayout()                
        layersTab.setLayout( layersLayout )
                               
        layer_selection_Layout = QHBoxLayout()      
        layer_selection_label = QLabel( "Select Layer:"  )
        layer_selection_Layout.addWidget( layer_selection_label ) 
        self.layersCombo =  QComboBox ( self )
        layer_selection_label.setBuddy( self.layersCombo )
#        layersCombo.setMaximumHeight( 30 )
        layer_selection_Layout.addWidget( self.layersCombo ) 
        
        for layer in self.layerList:               
            self.layersCombo.addItem( str(layer) ) 
        
        if self.layer:
            currentLayerIndex = self.layersCombo.findText ( self.layer )   
            if currentLayerIndex >= 0: self.layersCombo.setCurrentIndex( currentLayerIndex ) 
 
        layersLayout.addLayout( layer_selection_Layout )

    def sizeHint(self):
        return QSize(200,150)

    def updateController(self, controller):
        new_layer_value = str( self.layersCombo.currentText() )
        if new_layer_value <> self.layer: 
#            if self.pmod: self.pmod.changeVersion( self.layer, new_layer_value )
            self.persistParameter( 'layer', [ new_layer_value, ])  
            self.layer = new_layer_value
          
    def okTriggered(self, checked = False):
        """ okTriggered(checked: bool) -> None
        Update vistrail controller (if neccesssary) then close the widget
        
        """
        self.updateController(self.controller)
        self.emit(SIGNAL('doneConfigure()'))
        self.close()    
    
if __name__ == '__main__':  
     test = LayerConfigurationWidget( None, None )     
    
    
    
    
    