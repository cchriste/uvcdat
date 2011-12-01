from PyQt4 import QtGui, QtCore
import os
import cdms2
import uvcdatCommons
import customizeUVCDAT
import editVariableWidget
import axesWidgets
import  __main__
from gui.uvcdat.variable import VariableProperties

class QDefinedVariableWidget(QtGui.QWidget):
    """ QDefinedVariable contains a list of the user defined variables and allows the
    user to apply functions on defined variables """

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.setMinimumWidth(5*(customizeUVCDAT.iconsize*1.5))
        self.quickplotItem = None
        self.historyList=[]
        self.root=parent.root
        # Create Layout
        vbox = QtGui.QVBoxLayout()
        vbox.setMargin(0)
        self.setLayout(vbox)

        # Create Toolbar and add it to the layout
        self.createToolbar()
        vbox.addWidget(self.toolBar)

        # Create CommandLine for Simple Variable Operations
        ## self.command_line = QtGui.QLineEdit()
        ## self.command_line.setToolTip('Enter variable expression to generate a new variable (e.g., a = tas - ta + 10.0)')
        ## self.command_line.setText("defined variable command line")
        ## palette = self.command_line.palette()
        ## role = self.command_line.backgroundRole()
        ## #palette.setColor(role, QtGui.QColor(231,160,163))
        ## #palette.setColor(role, QtGui.QColor(246,204,174))
        ## palette.setColor(role, QtGui.QColor(184,212,240))
        ## #palette.setColor(role, QtGui.QColor(186,212,116))
        ## self.command_line.setPalette(palette)
        ## self.command_line.setAutoFillBackground(True)

        ## vbox.addWidget(self.command_line)

        # Create List for defined variables and add it to the layout
        self.varList = uvcdatCommons.QDragListWidget(type="definedVariables")
        self.varList.setToolTip("You can Drag and Drop Variables into most 'white' boxes")
        self.varList.setAlternatingRowColors(True)
        self.varList.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        self.varList.itemDoubleClicked.connect(self.variableDoubleClicked)
        vbox.addWidget(self.varList)

        # Connect Signals
        ## self.connect(self.varList, QtCore.SIGNAL('clicked(const QModelIndex&)'),
        ##              self.selectVariableFromListEvent)
        self.connect(self.varList, QtCore.SIGNAL('itemPressed( QListWidgetItem *)'),
                     self.selectVariableFromListEvent)

    def variableDoubleClicked(self,item):
        txt = str(item.text())
        #varProp = self.root.varProp
        self.root.varProp.parent=self
        for i in range(self.root.varProp.originTabWidget.count()):
            self.root.varProp.originTabWidget.removeTab(0)
        self.root.varProp.createEditTab()
        #print "OK axislist created with: ",txt.split()[1],__main__.__dict__[txt.split()[1]]
        axisList = axesWidgets.QAxisList(None,__main__.__dict__[txt.split()[1]],self)
        #axisList.setupVariableAxes()
        N=self.root.varProp.dimsLayout.count()
        while N>1:
            it = self.root.varProp.dimsLayout.takeAt(N-1)
            it.widget().deleteLater()
            it.widget().destroy()
            self.root.varProp.dimsLayout.removeItem(it)
            del(it)
            self.root.varProp.dims.update()
            self.root.varProp.update()
            self.update()
            N=self.root.varProp.dimsLayout.count()
        #varProp.dimsLayout.addWidget(axisList)
        #varProp.updateVarInfo(axisList)
        #self.root.varProp.setupEditTab(axisList.getVar())
        #self.root.varProp.originTabWidget.setCurrentIndex(1)
        self.root.varProp.setFloating(True)
        self.root.varProp.show()

    def defineQuickplot(self, file, var):
        """ When a user plots a variable that isn't explicitly defined a signal
        is emitted and this function is called to define the variable under
        the name 'quickplot'.  Replace the 'quickplot' variable if it
        already exists
        """
        if self.quickplotItem is None:
            self.quickplotItem = QDefinedVariableItem(file, self.root,var)
            self.varList.addItem(self.quickplotItem)
        else:
            self.quickplotItem.setVariable(var)
            self.quickplotItem.setFile(file)            


    def refreshVariablesStrings(self):
        # in case some var disapeearupdates the numbers
        selectedItems = self.getSelectedItems()
        N=len(selectedItems)
        items=self.getItems()
        nums=[]
        for item in items:
            try:
                num = int(str(item.text()).split()[0])
                nums.append(num)
            except:
                pass
        nums.sort()
        for item in selectedItems:
            val = int(str(item.text()).split()[0])
            item.updateVariableString(nums.index(val)+1)
            
            
    def getSelectedItems(self,project=True):
        """ Get a list of all of the defined tabnames / variables """
        selectedItems = self.varList.selectedItems()
        if project:
            varList = []
            current = id(self.root.workspace.currentProject)
            for item in selectedItems:
                if current in item.projects:
                    varList.append(item)
        else:
            varList=selectedItems
        return varList
    
    def getItems(self,project=True):
        """ Get a list of all of the defined tabnames / variables """
        varList = []
        current = id(self.root.workspace.currentProject)
        for i in range(self.varList.count()):
            item=self.varList.item(i)
            if project:
                if current in item.projects:
                    varList.append(item)
            else:
                varList.append(item)
        return varList

    def getSelectedDefinedVariables(self,project=True):
        """ Get a list of all of the defined tabnames / variables """
        selectedItems = self.varList.selectedItems()
        varList = []
        current = id(self.root.workspace.currentProject)
        for item in selectedItems:
            if project:
                if current in item.projects:
                    varList.append(item.getVariable())
            else:
                varList.append(item.getVariable())
        return varList

    def getVariable(self,name):
        for i in range(self.varList.count()):
            it = self.varList.item(i)
            if str(it.text()).split()[1] == name:
                return it.getVariable()

    def updateVars(self):
        for i in range(self.varList.count()):
            it = self.varList.item(i)
            ittxt = str(it.text())
            v = it.getVariable()
            if it.varName != v.id:
                it.setText(ittxt.replace(it.varName,v.id,1))
                iTab = self.root.tabView.widget(0).tabWidget.getTabIndexFromName(it.varName)
                self.root.tabView.widget(0).tabWidget.setTabText(iTab,v.id)
                del(__main__.__dict__[it.varName])
                it.varName = v.id
                self.root.stick_defvar_into_main_dict(v)
            
    def addVariable(self, var, type='CDMS'):
        """ Add variable into dict / list & emit signal to create
        a tab for the variable
        """
        if type == 'CDMS':
            self.root.stick_defvar_into_main_dict(var)
            item = QDefinedVariableItem(var,self.root)
            for i in range(self.varList.count()-1,-1,-1):
                if self.varList.item(i).getVarName() == var.id:
                    self.varList.takeItem(i)
        else:
            item = QtGui.QTreeWidgetItem(QtCore.QStringList(var))
        self.varList.addItem(item)
        # Recording define variable teaching command
#        self.recordDefineVariableTeachingCommand(varName, var.id, file, axesArgString)

        # emit signal to tell to update edit area
        ## print "Added variable"
        ## self.emit(QtCore.SIGNAL('setupDefinedVariableAxes'), var)
        
    def deleteVariable(self, varid):
        """ Add variable into dict / list & emit signal to create
        a tab for the variable
        """
        for i in range(self.varList.count()-1,-1,-1):
            if self.varList.item(i).getVarName() == varid:
                del(__main__.__dict__[varid])
                self.varList.takeItem(i)
        iTab = self.root.tabView.widget(0).tabWidget.getTabIndexFromName(varid)
        self.root.tabView.widget(0).tabWidget.removeTab(iTab)
        
    def unselectItems(self,items):
        selected = self.varList.selectedItems()
        for item in items:
            if item in selected:
                item.setSelected(False)
                self.selectVariableFromListEvent(item)

        
    def unselectVariableFromName(self,name):
        for i in range(self.varList.count()):
            it = self.varList.item(i)
            if str(it.text()).split()[1] == name:
                it.setSelected(False)
                self.selectVariableFromListEvent(it)
                break
    def selectVariableFromName(self,name):
        for i in range(self.varList.count()):
            it = self.varList.item(i)
            if str(it.text()).split()[1] == name:
                it.setSelected(True)
                self.selectVariableFromListEvent(it)
                break

    def selectAllVariables(self):
        selected = self.varList.selectedItems()
        for i in range(self.varList.count()):
            it = self.varList.item(i)
            if not it in selected:
                self.selectVariableFromName(it.varName)
    
    def selectVariableFromListEvent(self, item):
        """ Update the number next to the selected defined variable and
        send a signal to QVariableView to display the selected variable
        """
        ## print 'Ok we are where we should be'
        ## item = self.varList.item(modelIndex.row())
        selectedItems = self.getSelectedItems()
        # If the item is unselected then change the selection str back to '--'
        # and decrement all the numbers of the other selected vars that are
        # less than the number of the item that was unselected
        if item not in selectedItems:
            unselectedNum = item.getSelectNum()
            item.updateVariableString(None)
            
            for item in selectedItems:
                num = item.getSelectNum()
                if num > unselectedNum:
                    item.updateVariableString(item.getSelectNum() - 1)
        # If item is selected, change the selection str to a number
        else:
            N=len(selectedItems)
            if N==0:
                N=None
            item.updateVariableString(N)

        # Send signal of all selected vars to qvariableview and bring up the
        # most recently selected variable's tab
        var = item.getVariable()
        ## selectedVars = [item.getVariable() for item in selectedItems]
        tabName = item.getVarName()
        
        self.emit(QtCore.SIGNAL('selectDefinedVariableEvent'), tabName, var)

    def isVariableDefined(self, varID):
        """ Return true if a variable with the given id is defined (this does
        not include 'quickplot' """
        
        for i in range(self.varList.count()):
            item = self.varList.item(i)
            if varID == item.getVariable().id and not item.isQuickplotItem():
                return True
        return False

    ## def getItem(self, varID):
    ##     """ Return the item with the defined variable with name = varID """
    ##     for i in range(self.varList.count()):
    ##         listItem = self.varList.item(i)
    ##         if varID == listItem.getVariable().id:
    ##             return listItem
    ##     return None  

    def recordDefineVariableTeachingCommand(self, name, varName, file, axesArgString):
        if varName in list(getattr(file, 'variables')):
            fileID = "fid2"            
            command = '\n# Get new slab\n'
            command += "%s = %s('%s', %s)\n" %(name, fileID, varName, axesArgString)        

            self.emit(QtCore.SIGNAL('recordTeachingCommand'), command)

    def editVariables(self):
        self.eds=[]
        sel = self.getSelectedDefinedVariables()
        if len(sel)==0:
            return
        for s in sel:
            d=VariableProperties(self,mode="edit")
            #d=QtGui.QDialog(self)
            axisList = axesWidgets.QAxisList(None,s,self)
            axisList.setupVariableAxes()
            l=QtGui.QVBoxLayout()
            #d.setLayout(l)
            d.dimsLayout.addWidget(axisList)
            d.updateVarInfo(axisList)
            d.setupEditTab(axisList.getVar())
            d.originTabWidget.setCurrentIndex(1)
            #e = editVariableWidget.editVariableWidget(s,parent=d,root=self.root)
            #print s,d,self
            #l.addWidget(e)
            d.show()
            
            self.eds.append(d)
        

    def saveVariables(self):
        sel = self.getSelectedDefinedVariables()
        if len(sel)==0:
            return
        out = QtGui.QFileDialog.getSaveFileName(self,"NetCDF File",filter="NetCDF Files (*.nc *.cdg *.NC *.CDF *.nc4 *.NC4) ;; All Files (*.*)",options=QtGui.QFileDialog.DontConfirmOverwrite)
        mode = "w"
        if os.path.exists(out):
            overwrite = QtGui.QMessageBox.question(self,"Existing File","Do you want to append to it or overwrite it?","Append","Overwrite","Ooops",2)
            if overwrite == 2:
                return
            elif overwrite == 0:
                mode="r+"

        c = self.cursor()
        self.setCursor(QtCore.Qt.BusyCursor)
        try:
            fo = cdms2.open(str(out),mode)
            for v in sel:
                fo.write(v)
            fo.close()
        except Exception,err:
            QtGui.QMessageBox.question(self,"Existing File","Error while saving variables: %s" % err)
        self.setCursor(c)
            
    def variableInfo(self):
        self.ieds=[]
        class MyLog():
            def __init__(self):
                self.text=""
            def write(self,text):
                self.text+=text
            def clear(self):
                self.text=""
        mylog = MyLog()
        for v in self.getSelectedDefinedVariables():
            d = QtGui.QDialog()
            l = QtGui.QVBoxLayout()
            d.setLayout(l)
            lb = QtGui.QLabel("Variable: %s %s" % (v.id,repr(v.shape)))
            l.addWidget(lb)
            te = QtGui.QTextEdit()
            v.info(device=mylog)
            f = te.currentFont()
            fm = QtGui.QFontMetrics(f)
            minWidth = min(max(map(fm.width,mylog.text.split("\n"))),65*fm.width("W"))
            minHeight = min(len(mylog.text.split()),30)
            te.setMinimumHeight(fm.height()*minHeight)
            te.setMinimumWidth(minWidth)
            te.setText(mylog.text)
            te.setReadOnly(True)
            mylog.clear()
            l.addWidget(te)
            b = QtGui.QPushButton("Close")
            l.addWidget(b)
            self.connect(b,QtCore.SIGNAL("clicked()"),d.hide)
            d.show()
            self.ieds.append(d)
            
    def trashVariable(self):
        for v in self.getSelectedDefinedVariables():
            self.deleteVariable(v.id)
            
    def trashAll(self):
        self.selectAllVariables()
        for v in self.getSelectedDefinedVariables():
            self.deleteVariable(v.id)
        
    def newVariable(self):
        varProp = self.root.varProp
        varProp.setFloating(True)
        varProp.show()
                
    def createToolbar(self):
        ICONPATH = customizeUVCDAT.ICONPATH

        # Create options bar
        self.toolBar = QtGui.QToolBar()
        self.toolBar.setIconSize(QtCore.QSize(customizeUVCDAT.iconsize,customizeUVCDAT.iconsize))
        actionInfo = [
            ('symbol_add.ico', "add",'Add variable(s).',self.newVariable),
            ('symbol_delete.ico', "del",'Delete selected defined variable(s).',self.trashVariable),
            ('symbol_check.ico', "recycle",'Select ALL variables.',self.selectAllVariables),
            ('symbol_information.ico', "info",'Display selected defined variable(s) information.',self.variableInfo),
            ('pencil.ico', "edit",'Edit selected defined variable(s).',self.editVariables),
            ('floppy_disk_blue.ico', "save",'Save selected defined variable(s) to a netCDF file.',self.saveVariables),
            ## ('log.gif', "log",'Logged information about the defined variables.',self.variablesInfo),
            ## ('trashcan_empty.gif', "trash",'Defined variable items that can be disposed of permanetly or restored.',self.empytTrash),
            ]
        
        for info in actionInfo:
            icon = QtGui.QIcon(os.path.join(ICONPATH, info[0]))
            action = self.toolBar.addAction(icon, info[1])
            action.setStatusTip(info[2])
            action.setToolTip(info[2])
            self.connect(action,QtCore.SIGNAL("triggered()"),info[3])
            
        ## self.toolBar.addSeparator()

        ## self.opButton = QtGui.QToolButton()
        ## self.opButton.setText('Ops')
        
        ## # Create Operations Menu
        ## menu = QtGui.QMenu(self)
        ## grid = QtGui.QGridLayout()
        ## grid.setMargin(0)
        ## grid.setSpacing(0)
        ## menu.setLayout(grid)
        ## opDefs =[
        ##     ['Add a number or two (or more)\nselected Defined Variables.\n(Can be used as "or")','add.gif','add'],
        ##     ['Subtract a number or two (or more)\nselected Defined Variables.','subtract.gif','subtract'],
        ##     ['Multiply a number or two (or more)\nselected Defined Variables.\n(Can be used as "and")','multiply.gif','multiply'],
        ##     ['Divide a number or two (or more)\nselected Defined Variables.','divide.gif','divide'],
        ##     ['"Grows" variable 1 and variable 2 so that they end up having the same dimensions\n(order of variable 1 plus any extra dims)','grower.gif','grower'],
        ##     ['Spatially regrid the first selected Defined Variable\nto the second selected Defined Variable.','regrid.gif','regrid'],
        ##     ['Mask variable 2 where variable 1 is "true".','mask.gif','mask'],
        ##     ['Get variable mask','getmask.gif','getmask'],
        ##     ['Return true where variable 1 is less than variable 2 (or number)','less.gif','less'],
        ##     ['Return true where variable 1 is greater than variable 2 (or number)','greater.gif','greater'],
        ##     ['Return true where variable 1 is equal than variable 2 (or number)','equal.gif','equal'],
        ##     ['Return not of variable','not.gif','not'],
        ##     ['Compute the standard deviation\n(over first axis)','std.gif','std'],
        ##     ['Power (i.e., x ** y) of the most recently\nselected two Defined Variables, where\nx = variable 1 and y = variable 2 or float number.','power.gif','power'],
        ##     ['Exp (i.e., e ** x) of the most recently\nselected Defined Variable.','exp.gif','exp'],
        ##     ['Log (i.e., natural log) of the most recently\nselected Defined Variable.','mlog.gif','log'],
        ##     ['Base10 (i.e., 10 ** x) of the most recently\nselected Defined Variable.','base10.gif','base10'],
        ##     ['Log10 (i.e., log base 10) of the most\nrecently selected Defined Variable. ','mlog10.gif','log10'],
        ##     ['Inverse (i.e., 1/x) of the most recently\nselected Defined Variable.','inverse.gif','inverse'],
        ##     ['Abs (i.e., absolute value of x) of the most\nrecently selected Defined Variable.','fabs.gif','fabs'],
        ##     ['Sine (i.e., sin) of the most recently\nselected Defined Variable.','sin.gif','sin'],
        ##     ['Hyperbolic sine (i.e., sinh) of the most recently\nselected Defined Variable.','sinh.gif','sinh'],
        ##     ['Cosine (i.e., cos) of the most recently\nselected Defined Variable.','cos.gif', 'cos'],
        ##     ['Hyperbolic cosine (i.e., cosh) of the most recently\nselected Defined Variable.','cosh.gif','cosh'],
        ##     ['Tangent (i.e., tan) of the most recently\nselected Defined Variable.','tan.gif','tan'],
        ##     ['Hyperbolic tangent (i.e., tanh) of the most recently\nselected Defined Variable.','tanh.gif','tanh'],
        ##     ]
        ## self.opActions = []
        ## for i in xrange(len(opDefs)):
        ##     action = QtGui.QAction(QtGui.QIcon(os.path.join(ICONPATH, opDefs[i][1])), opDefs[i][2], menu)
        ##     action.setStatusTip(opDefs[i][0])
        ##     action.setToolTip(opDefs[i][0])
        ##     self.opActions.append(action)
        ##     b = QtGui.QToolButton()
        ##     b.setDefaultAction(action)
        ##     grid.addWidget(b, i/2, i%2)

        ## self.opButton.setMenu(menu)
        ## self.opButton.setPopupMode(QtGui.QToolButton.InstantPopup)
        ## self.connect(self.opButton, QtCore.SIGNAL('clicked(bool)'), self.opButton.showMenu)
        
        ## self.toolBar.addWidget(self.opButton)

class QDefinedVariableItem(QtGui.QListWidgetItem):
    """ Item to be stored by QDefinedVariable's list widget """
    
    def __init__(self, variable, root, parent=None,project=None):
        QtGui.QListWidgetItem.__init__(self, parent)
        self.varName = variable.id # This is also the tabname
        self.variable = variable
        self.root=root
        if project is None:
            current = id(self.root.workspace.currentProject)
            self.projects = [current,]
            
        self.updateVariableString(None)

    def getVariable(self):
        return self.variable

    def getVarName(self):
        return self.varName

    def getFile(self):
        return self.cdmsFile

    def getSelectNum(self):
        return self.selectNum
        
    def isQuickplotItem(self):
        return self.varName == 'quickplot'
        
    def updateVariableString(self, num=None):
        """ updateVariableString(num: int)

        Update the variable string that is shown to the user in the list.
        format =  '-- variableName (shape)', where num is the selection number
        """
        if num is None:
            self.selectNum = -1
            numString = '--'
        else:
            self.selectNum = num
            numString = str(num).zfill(2)

        varString = "%s %s %s" % (numString, self.varName, str(self.variable.shape))
        self.setData(0, QtCore.QVariant(QtCore.QString(varString)))

    def setFile(self, cdmsFile):
        self.cdmsFile = cdmsFile
        
    def setVariable(self, variable):
        """ Set the variable and update the variable string that is shown to the
        user in the list
        """
        self.variable = variable
        self.updateVariableString()

class QDefVarWarningBox(QtGui.QDialog):
    """ Popup box to warn a user that a variable with same name is already
    defined. Contains a line edit to allow a user to enter a new variable
    name or to replace the existing defined variable """

    def __init__(self, parent=None):
        QtGui.QDialog.__init__(self, parent)
        self.varID = None

        # Init layout
        vbox = QtGui.QVBoxLayout()
        hbox = QtGui.QHBoxLayout()
        hbox.setDirection(QtGui.QBoxLayout.RightToLeft)
        vbox.setSpacing(10)

        # Add LineEdit
        self.text = QtGui.QLabel()
        self.lineEdit = QtGui.QLineEdit()

        # Add OK / Cancel Buttons
        okButton = QtGui.QPushButton('OK')
        cancelButton = QtGui.QPushButton('Cancel')
        hbox.addWidget(cancelButton)        
        hbox.addWidget(okButton)

        vbox.addWidget(self.text)
        vbox.addWidget(self.lineEdit)
        vbox.addLayout(hbox)
        self.setLayout(vbox)

        # Connect Signals
        self.connect(okButton, QtCore.SIGNAL('pressed()'), self.okPressedEvent)
        self.connect(cancelButton, QtCore.SIGNAL('pressed()'), self.close)
        self.connect(self.lineEdit, QtCore.SIGNAL('returnPressed()'), self.okPressedEvent)

    def showWarning(self, varID, file, var, axesArgString):
        """ Show warning message and prompt user for a new variable name. Or use
        the same var name to replace the existing defined variable """
        
        self.varID = varID
        self.file = file
        self.var = var
        self.axesArgString = axesArgString
        
        message = "'%s' has already been defined.  Enter a new variable name \n or press 'OK' to replace '%s'" %(varID, varID)
        self.text.setText(message)
        self.lineEdit.setText(varID)

        self.open()

    def okPressedEvent(self):
        self.varID = self.lineEdit.text() # get the user entered variable name
        self.close()        

        # Emit signal to QDefinedVar to indicate it's ok to add the variable to defined list
        self.emit(QtCore.SIGNAL('newVarID'),
                  self.varID, self.file, self.var, self.axesArgString)
