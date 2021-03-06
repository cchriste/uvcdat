'''
Created on Nov 21, 2011

@author: tpmaxwel
'''
import vtk, sys, os, copy, time, traceback
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from packages.vtDV3D.InteractiveConfiguration import *
from core.modules.vistrails_module import Module, ModuleError
from core.uvcdat.plot_pipeline_helper import PlotPipelineHelper
from packages.uvcdat_cdms.init import CDMSVariable, CDMSVariableOperation 
from packages.vtDV3D.WorkflowModule import WorkflowModule 
from packages.vtDV3D import ModuleStore
from packages.vtDV3D.vtUtilities import *
from packages.vtDV3D.PersistentModule import *
import cdms2, cdtime, cdutil, MV2 
PortDataVersion = 0

def getRoiSize( roi ):
    if roi == None: return 0
    return abs((roi[2]-roi[0])*(roi[3]-roi[1]))

def getTitle( dsid, name, attributes, showUnits=False ):
       long_name = attributes.get( 'long_name', attributes.get( 'standard_name', name ) )
       if not showUnits: return "%s:%s" % ( dsid, long_name )
       units = attributes.get( 'units', 'unitless' )
       return  "%s:%s (%s)" % ( dsid, long_name, units )
   
def isDesignated( axis ):
    return ( axis.isLatitude() or axis.isLongitude() or axis.isLevel() or axis.isTime() )

def matchesAxisType( axis, axis_attr, axis_aliases ):
    matches = False
    aname = axis.id.lower()
    axis_attribute = axis.attributes.get('axis',None)
    if axis_attribute and ( axis_attribute.lower() in axis_attr ):
        matches = True
    else:
        for axis_alias in axis_aliases:
            if ( aname.find( axis_alias ) >= 0): 
                matches = True
                break
    return matches

class AxisType:
    NONE = 0
    Time = 1
    Longitude = 2
    Latitude = 3
    Level = 4
    lev_aliases = [ 'bottom', 'top', 'zdim' ]
    lev_axis_attr = [ 'z' ]
    lat_aliases = [ 'north', 'south', 'ydim' ]
    lat_axis_attr = [ 'y' ]
    lon_aliases = [ 'east', 'west', 'xdim' ]
    lon_axis_attr = [ 'x' ]

def getAxisType( axis ):
    if axis.isLevel() or matchesAxisType( axis, AxisType.lev_axis_attr, AxisType.lev_aliases ):
        return AxisType.Level      
    elif axis.isLatitude() or matchesAxisType( axis, AxisType.lat_axis_attr, AxisType.lat_aliases ):
        return AxisType.Latitude                   
    elif axis.isLongitude() or matchesAxisType( axis, AxisType.lon_axis_attr, AxisType.lon_aliases ):
        return AxisType.Longitude     
    elif axis.isTime():
        return AxisType.Time
    else: return  AxisType.NONE    

def designateAxisType( self, axis ):
    if not isDesignated( axis ):
        if matchesAxisType( axis, AxisType.lev_axis_attr, AxisType.lev_aliases ):
            axis.designateLevel() 
            return AxisType.Level         
        elif matchesAxisType( axis, AxisType.lat_axis_attr, AxisType.lat_aliases ):
            axis.designateLatitude() 
            return AxisType.Latitude                    
        elif matchesAxisType( axis, AxisType.lon_axis_attr, AxisType.lon_aliases ):
            axis.designateLongitude()
            return AxisType.Longitude    
    return getAxisType( axis )

                   
class PM_CDMSDataReader( PersistentVisualizationModule ):
    
    dataCache = {}
    imageDataCache = {}

    def __init__(self, mid, **args):
        PersistentVisualizationModule.__init__( self, mid, createColormap=False, requiresPrimaryInput=False, layerDepParms=['portData'], **args)
        self.datasetId = None
        self.fileSpecs = None
        self.varSpecs = None
        self.gridSpecs = None
        self.currentTime = 0
        self.currentLevel = None
        self.timeIndex = 0
        self.useTimeIndex = False
        self.timeAxis = None
        if self.outputType == CDMSDataType.Hoffmuller:
            self.addUVCDATConfigGuiFunction( 'chooseLevel', LevelConfigurationDialog, 'L', label='Choose Level' ) 
            
    def getTimeAxis(self):
        return self.timeAxis
       
    def getImageDataCache(self):
        return self.imageDataCache.setdefault( self.moduleID, {} )

    @classmethod
    def clearCache(cls):
        for varDataSpecs in cls.dataCache.values():
            varDataMap = varDataSpecs.get('varData', None )
            if varDataMap:
                try:
                    dataArray = varDataMap[ 'newDataArray']
                    del dataArray 
                except: pass
            del varDataSpecs
        cls.dataCache.clear()
        for imageDataMap in cls.imageDataCache.values():
            for imageData in imageDataMap.values():
                del imageData
        cls.imageDataCache.clear()
        
    def getCachedData( self, varDataId ):
        varData = self.dataCache.setdefault( varDataId, {} )
        return varData.get( 'varData', None )

    def setCachedData(self, varDataId, varDataMap ):
        varData = self.dataCache.setdefault( varDataId, {} )
        varData[ 'varData' ] = varDataMap
                
    def getParameterDisplay( self, parmName, parmValue ):
        if parmName == 'timestep':
#            timestep = self.getTimeIndex( int( parmValue[0] ) )
            timestep = int( parmValue[0] )
            try:    return str( self.timeLabels[ timestep ] ), 10
            except: pass
        return None, 1

    def addCDMSVariable( self, cdms_var, index ):
        dsetId = "Computed"
        var = None
        varname = None
        if issubclass( cdms_var.__class__, CDMSVariableOperation ):
            varname = cdms_var.outvar.name
            var =  cdms_var.outvar.var
        else:
            varname = cdms_var.name
            var = cdms_var.var
            if cdms_var.file : dsetId = cdms_var.file
        self.cdmsDataset.addTransientVariable( varname, var )
        self.cdmsDataset.setVariableRecord( "VariableName%d" % index, '*'.join( [ dsetId, varname ] ) )
        return var, dsetId
    
    def designateAxes(self,var):
        lev_aliases = [ 'bottom', 'top', 'zdim' ]
        lev_axis_attr = [ 'z' ]
        lat_aliases = [ 'north', 'south', 'ydim' ]
        lat_axis_attr = [ 'y' ]
        lon_aliases = [ 'east', 'west', 'xdim' ]
        lon_axis_attr = [ 'x' ]
        for axis in var.getAxisList():
            if not isDesignated( axis ):
                if matchesAxisType( axis, lev_axis_attr, lev_aliases ):
                    axis.designateLevel()
                    print " --> Designating axis %s as a Level axis " % axis.id            
                elif matchesAxisType( axis, lat_axis_attr, lat_aliases ):
                    axis.designateLatitude()
                    print " --> Designating axis %s as a Latitude axis " % axis.id                     
                elif matchesAxisType( axis, lon_axis_attr, lon_aliases ):
                    axis.designateLongitude()
                    print " --> Designating axis %s as a Longitude axis " % axis.id 
           
    def execute(self, **args ):
        import api
        from packages.vtDV3D.CDMS_DatasetReaders import CDMSDataset
        cdms_vars = self.getInputValues( "variable"  ) 
        if cdms_vars and len(cdms_vars):
            iVar = 1
            cdms_var = cdms_vars.pop(0)
            self.cdmsDataset = CDMSDataset()
            var, dsetId = self.addCDMSVariable( cdms_var, iVar )
            self.newDataset = ( self.datasetId <> dsetId )
            if self.newDataset: ModuleStore.archiveCdmsDataset( dsetId, self.cdmsDataset )
            self.newLayerConfiguration = self.newDataset
            self.datasetId = dsetId
            self.designateAxes(var)
            self.nTimesteps = 1
            self.timeRange = [ 0, self.nTimesteps, 0.0, 0.0 ]
            self.timeAxis = var.getTime()
            if self.timeAxis:
                self.nTimesteps = len( self.timeAxis ) if self.timeAxis else 1
                try:
                    comp_time_values = self.timeAxis.asComponentTime()
                    t0 = comp_time_values[0].torel(self.referenceTimeUnits).value
                    if (t0 < 0):
                        self.referenceTimeUnits = self.timeAxis.units
                        t0 = comp_time_values[0].torel(self.referenceTimeUnits).value
                    dt = 0.0
                    if self.nTimesteps > 1:
                        t1 = comp_time_values[-1].torel(self.referenceTimeUnits).value
                        dt = (t1-t0)/(self.nTimesteps-1)
                        self.timeRange = [ 0, self.nTimesteps, t0, dt ]
                except:
                    values = self.timeAxis.getValue()
                    t0 = values[0] if len(values) > 0 else 0
                    t1 = values[-1] if len(values) > 1 else t0
                    dt = ( values[1] - values[0] )/( len(values) - 1 ) if len(values) > 1 else 0
                    self.timeRange = [ 0, self.nTimesteps, t0, dt ]
            self.setParameter( "timeRange" , self.timeRange )
            self.cdmsDataset.timeRange = self.timeRange
            self.cdmsDataset.referenceTimeUnits = self.referenceTimeUnits
            self.timeLabels = self.cdmsDataset.getTimeValues()
            timeData = args.get( 'timeData', [ self.cdmsDataset.timeRange[2], 0, False ] )
            self.timeValue = cdtime.reltime( float(timeData[0]), self.referenceTimeUnits )
            self.timeIndex = timeData[1]
            self.useTimeIndex = timeData[2]
#            print "Set Time [mid = %d]: %s, NTS: %d, Range: %s, Index: %d (use: %s)" % ( self.moduleID, str(self.timeValue), self.nTimesteps, str(self.timeRange), self.timeIndex, str(self.useTimeIndex) )
#            print "Time Step Labels: %s" % str( self.timeLabels )
            intersectedRoi = self.cdmsDataset.gridBounds
            intersectedRoi = self.getIntersectedRoi( cdms_var, intersectedRoi )
            while( len(cdms_vars) ):
                cdms_var2 = cdms_vars.pop(0)
                if cdms_var2: 
                    iVar = iVar+1
                    self.addCDMSVariable( cdms_var2, iVar )
                    intersectedRoi = self.getIntersectedRoi( cdms_var2, intersectedRoi )
                  
            for iVarInputIndex in range( 2,5 ):
                cdms_var2 = self.getInputValue( "variable%d" % iVarInputIndex  ) 
                if cdms_var2: 
                    iVar = iVar+1
                    self.addCDMSVariable( cdms_var2, iVar )
                    intersectedRoi = self.getIntersectedRoi( cdms_var2, intersectedRoi )
                    
            self.generateOutput(roi=intersectedRoi)
#            if self.newDataset: self.addAnnotation( "datasetId", self.datasetId )
        else:
            dset = self.getInputValue( "dataset"  ) 
            if dset: 
                self.cdmsDataset = dset
#                dsetid = self.getAnnotation( "datasetId" )
#                if dsetid: self.datasetId = dsetid 
                dsetId = self.cdmsDataset.getDsetId()
#                self.newDataset = ( self.datasetId <> dsetId )
                self.newLayerConfiguration = True # self.newDataset
                self.datasetId = dsetId
                ModuleStore.archiveCdmsDataset( self.datasetId, self.cdmsDataset )
                self.timeRange = self.cdmsDataset.timeRange
                timeData = args.get( 'timeData', [ self.cdmsDataset.timeRange[2], 0, False ] )
                self.timeValue = cdtime.reltime( float(timeData[0]), self.referenceTimeUnits )
                self.timeIndex = timeData[1]
                self.useTimeIndex = timeData[2]
                self.timeLabels = self.cdmsDataset.getTimeValues()
                self.nTimesteps = self.timeRange[1]
#                print "Set Time: %s, NTS: %d, Range: %s, Index: %d (use: %s)" % ( str(self.timeValue), self.nTimesteps, str(self.timeRange), self.timeIndex, str(self.useTimeIndex) )
#                print "Time Step Labels: %s" % str( self.timeLabels ) 
                self.generateOutput()
#                if self.newDataset: self.addAnnotation( "datasetId", self.datasetId )
 
            
    def getParameterId(self):
        return self.datasetId
            
    def getPortData( self, **args ):
        return self.getInputValue( "portData", **args )  

    def generateVariableOutput( self, cdms_var ): 
        print str(cdms_var.var)
        self.set3DOutput( name=cdms_var.name,  output=cdms_var.var )

    def refreshVersion(self):
        portData = self.getPortData()
        if portData:
            portDataVersion = portData[1] + 1
            serializedPortData = portData[0]
            self.persistParameter( 'portData', [ serializedPortData, portDataVersion ] )
        
    def getOutputRecord( self, ndim = -1 ):
        portData = self.getPortData()
        if portData:
            oRecMgr = OutputRecManager( portData[0]  )
            orecs = oRecMgr.getOutputRecs( self.datasetId ) if oRecMgr else None
            if not orecs: raise ModuleError( self, 'No Variable selected for dataset %s.' % self.datasetId )             
            for orec in orecs:
                if (ndim < 0 ) or (orec.ndim == ndim): return orec
        return None
             
    def generateOutput( self, **args ): 
        oRecMgr = None 
        varRecs = self.cdmsDataset.getVarRecValues()
        if len( varRecs ):
#            print " VolumeReader->generateOutput, varSpecs: ", str(varRecs)
            oRecMgr = OutputRecManager() 
#            varCombo = QComboBox()
#            for var in varRecs: varCombo.addItem( str(var) ) 
            orec = OutputRec( 'volume', ndim=3, varList=varRecs )  # varComboList=[ varCombo ], 
            oRecMgr.addOutputRec( self.datasetId, orec ) 
        else:
            portData = self.getPortData()
            if portData:
#                print " VolumeReader->generateOutput, portData: ", portData
                oRecMgr = OutputRecManager( portData[0]  )
        orecs = oRecMgr.getOutputRecs( self.datasetId ) if oRecMgr else None
        if not orecs: raise ModuleError( self, 'No Variable selected for dataset %s.' % self.datasetId )             
        for orec in orecs:
            cachedImageDataName = self.getImageData( orec, **args ) 
            if cachedImageDataName: 
                imageDataCache = self.getImageDataCache()            
                if   orec.ndim >= 3: self.set3DOutput( name=orec.name,  output=imageDataCache[cachedImageDataName] )
                elif orec.ndim == 2: self.set2DOutput( name=orec.name,  output=imageDataCache[cachedImageDataName] )
        self.currentTime = self.getTimestep()
     
    def getTimestep( self ):
        dt = self.timeRange[3]
        return 0 if dt <= 0.0 else int( round( ( self.timeValue.value - self.timeRange[2] ) / dt ) )

    def setCurrentLevel(self, level ): 
        self.currentLevel = level
               
    def getImageData( self, orec, **args ):
        """
        This method converts cdat data into vtkImageData objects. The ds object is a CDMSDataset instance which wraps a CDAT CDMS Dataset object. 
        The ds.getVarDataCube method execution extracts a CDMS variable object (varName) and then cuts out a data slice with the correct axis ordering (returning a NumPy masked array).   
        The array is then rescaled, converted to a 1D unsigned short array, and then wrapped as a vtkUnsignedShortArray using the vtkdata.SetVoidArray method call.  
        The vtk data array is then attached as point data to a vtkImageData object, which is returned.
        The CDAT metadata is serialized, wrapped as a vtkStringArray, and then attached as field data to the vtkImageData object.  
        """
        varList = orec.varList
        npts = -1
        dataDebug = False
        if len( varList ) == 0: return False
        varDataIds = []
        intersectedRoi = args.get('roi', None )
        if intersectedRoi: self.cdmsDataset.setRoi( intersectedRoi )
        exampleVarDataSpecs = None
        dsid = None
        if (self.outputType == CDMSDataType.Vector ) and len(varList) < 3:
            if len(varList) == 2: 
                imageDataName = getItem( varList[0] )
                dsid = imageDataName.split('*')[0]
                varList.append( '*'.join( [ dsid, '__zeros__' ] ) )
            else: 
                print>>sys.stderr, "Not enough components for vector plot: %d" % len(varList)
#        print " Get Image Data: varList = %s " % str( varList )
        for varRec in varList:
            range_min, range_max, scale, shift  = 0.0, 0.0, 1.0, 0.0   
            imageDataName = getItem( varRec )
            varNameComponents = imageDataName.split('*')
            if len( varNameComponents ) == 1:
                dsid = self.cdmsDataset.getReferenceDsetId() 
                varName = varNameComponents[0]
            else:
                dsid = varNameComponents[0]
                varName = varNameComponents[1]
            ds = self.cdmsDataset[ dsid ]
            self.timeRange = self.cdmsDataset.timeRange
            portName = orec.name
            selectedLevel = orec.getSelectedLevel() if ( self.currentLevel == None ) else self.currentLevel
            ndim = 3 if ( orec.ndim == 4 ) else orec.ndim
            default_dtype = np.ushort if ( (self.outputType == CDMSDataType.Volume ) or (self.outputType == CDMSDataType.Hoffmuller ) )  else np.float 
            scalar_dtype = args.get( "dtype", default_dtype )
            self._max_scalar_value = getMaxScalarValue( scalar_dtype )
            self._range = [ 0.0, self._max_scalar_value ]  
            datatype = getDatatypeString( scalar_dtype )
            iTimestep = 0 if varName == '__zeros__' else self.timeIndex if self.useTimeIndex else self.getTimestep()
            varDataIdIndex = iTimestep
            if (self.outputType == CDMSDataType.Hoffmuller):
                if ( selectedLevel == None ):
                    varDataIdIndex = 0
                else:
                    varDataIdIndex = selectedLevel

            roiStr = ":".join( [ ( "%.1f" % self.cdmsDataset.gridBounds[i] ) for i in range(4) ] ) if self.cdmsDataset.gridBounds else ""
            varDataId = '%s;%s;%d;%s;%s' % ( dsid, varName, self.outputType, str(varDataIdIndex), roiStr )
            varDataIds.append( varDataId )
            varDataSpecs = self.getCachedData( varDataId ) 
            flatArray = None
            if varDataSpecs == None:
                if varName == '__zeros__':
                    assert( npts > 0 )
                    newDataArray = np.zeros( npts, dtype=scalar_dtype ) 
                    varDataSpecs = copy.deepcopy( exampleVarDataSpecs )
                    varDataSpecs['newDataArray'] = newDataArray.ravel('F')  
                    self.setCachedData( varName, varDataSpecs ) 
                else: 
                    tval = None if (self.outputType == CDMSDataType.Hoffmuller) else [ self.timeValue, iTimestep, self.useTimeIndex ] 
                    varData = self.cdmsDataset.getVarDataCube( dsid, varName, tval, selectedLevel )
                    if varData.id <> 'NULL':
                        varDataSpecs = self.getGridSpecs( varData, self.cdmsDataset.gridBounds, self.cdmsDataset.zscale, self.outputType, ds )
                        if (exampleVarDataSpecs == None) and (varDataSpecs <> None): exampleVarDataSpecs = varDataSpecs
                        range_min = varData.min()
                        if type( range_min ).__name__ == "MaskedConstant": range_min = 0.0
                        range_max = varData.max()
                        if type( range_max ).__name__ == 'MaskedConstant': range_max = 0.0
                        newDataArray = varData
                                                          
                        if scalar_dtype == np.float:
                            newDataArray = newDataArray.filled( 1.0e-15 * range_min )
                        else:
                            shift = -range_min
                            scale = ( self._max_scalar_value ) / ( range_max - range_min ) if  ( range_max > range_min ) else 1.0        
                            rescaledDataArray = ( ( newDataArray + shift ) * scale )
                            newDataArray = rescaledDataArray.astype(scalar_dtype) 
                            newDataArray = newDataArray.filled( 0 )
                        
                        if dataDebug: self.dumpData( varName, newDataArray )
                        flatArray = newDataArray.ravel('F') 
                        array_size = flatArray.size
                        if npts == -1:  npts = array_size
                        else:           assert( npts == array_size )
                            
                        var_md = copy.copy( varData.attributes )
                        var_md[ 'range' ] = ( range_min, range_max )
                        var_md[ 'scale' ] = ( shift, scale )   
                        varDataSpecs['newDataArray'] = flatArray                     
                        md =  varDataSpecs['md']                 
                        md['datatype'] = datatype
                        md['timeValue']= self.timeValue.value
                        md['timeUnits' ] = self.referenceTimeUnits
                        md[ 'attributes' ] = var_md
                        md[ 'plotType' ] = 'zyt' if (self.outputType == CDMSDataType.Hoffmuller) else 'xyz'
                                        
                self.setCachedData( varDataId, varDataSpecs )  
        
        if not varDataSpecs: return None            
        cachedImageDataName = '-'.join( varDataIds )
        imageDataCache = self.getImageDataCache() 
        if not ( cachedImageDataName in imageDataCache ):
#            print 'Building Image for cache: %s ' % cachedImageDataName
            image_data = vtk.vtkImageData() 
            outputOrigin = varDataSpecs[ 'outputOrigin' ]
            outputExtent = varDataSpecs[ 'outputExtent' ]
            gridSpacing = varDataSpecs[ 'gridSpacing' ]
            if   scalar_dtype == np.ushort: image_data.SetScalarTypeToUnsignedShort()
            elif scalar_dtype == np.ubyte:  image_data.SetScalarTypeToUnsignedChar()
            elif scalar_dtype == np.float:  image_data.SetScalarTypeToFloat()
            image_data.SetOrigin( outputOrigin[0], outputOrigin[1], outputOrigin[2] )
#            image_data.SetOrigin( 0.0, 0.0, 0.0 )
            if ndim == 3: extent = [ outputExtent[0], outputExtent[1], outputExtent[2], outputExtent[3], outputExtent[4], outputExtent[5] ]   
            elif ndim == 2: extent = [ outputExtent[0], outputExtent[1], outputExtent[2], outputExtent[3], 0, 0 ]   
            image_data.SetExtent( extent )
            image_data.SetWholeExtent( extent )
            image_data.SetSpacing(  gridSpacing[0], gridSpacing[1], gridSpacing[2] )
#            print " ********************* Create Image Data, extent = %s, spacing = %s ********************* " % ( str(extent), str(gridSpacing) )
#            offset = ( -gridSpacing[0]*gridExtent[0], -gridSpacing[1]*gridExtent[2], -gridSpacing[2]*gridExtent[4] )
            imageDataCache[ cachedImageDataName ] = image_data
                
        image_data = imageDataCache[ cachedImageDataName ]
        nVars = len( varList )
#        npts = image_data.GetNumberOfPoints()
        pointData = image_data.GetPointData()
        for aname in range( pointData.GetNumberOfArrays() ): 
            pointData.RemoveArray( pointData.GetArrayName(aname) )
        fieldData = self.getFieldData()
        na = fieldData.GetNumberOfArrays()
        for ia in range(na):
            aname = fieldData.GetArrayName(ia)
            if aname.startswith('metadata'):
                fieldData.RemoveArray(aname)
#                print 'Remove fieldData Array: %s ' % aname
        extent = image_data.GetExtent()    
        scalars, nTup = None, 0
        vars = []      
        for varDataId in varDataIds:
            try: 
                varDataSpecs = self.getCachedData( varDataId )   
                newDataArray = varDataSpecs.get( 'newDataArray', None )
                md = varDataSpecs[ 'md' ] 
                varName = varDataId.split(';')[1]
                var_md = md[ 'attributes' ]            
                if newDataArray <> None:
                    vars.append( varName ) 
                    md[ 'valueRange'] = var_md[ 'range' ] 
                    vtkdata = getNewVtkDataArray( scalar_dtype )
                    nTup = newDataArray.size
                    vtkdata.SetNumberOfTuples( nTup )
                    vtkdata.SetNumberOfComponents( 1 )
                    vtkdata.SetVoidArray( newDataArray, newDataArray.size, 1 )
                    vtkdata.SetName( varName )
                    vtkdata.Modified()
                    pointData.AddArray( vtkdata )
#                    print "Add array to PointData: %s " % ( varName  )  
                    if (scalars == None) and (varName <> '__zeros__'):
                        scalars = varName
                        pointData.SetActiveScalars( varName  ) 
                        md[ 'scalars'] = varName 
            except Exception, err:
                print>>sys.stderr, "Error creating variable metadata: %s " % str(err)
                traceback.print_exc()
        for iArray in range(2):
            scalars = pointData.GetArray(iArray) 
#            print "Add array %d to PointData: %s (%s)" % ( iArray, pointData.GetArrayName(iArray), scalars.GetName()  )       
        try:                           
            if (self.outputType == CDMSDataType.Vector ): 
                vtkdata = getNewVtkDataArray( scalar_dtype )
                vtkdata.SetNumberOfComponents( 3 )
                vtkdata.SetNumberOfTuples( nTup )
                iComp = 0
                for varName in vars:
                    fromArray =  pointData.GetArray( varName )
                    fromNTup = fromArray.GetNumberOfTuples()
                    tup0 = fromArray.GetValue(0)
                    toNTup = vtkdata.GetNumberOfTuples()
                    vtkdata.CopyComponent( iComp, fromArray, 0 )
                    if iComp == 0: 
                        md[ 'scalars'] = varName 
                    iComp = iComp + 1                    
                vtkdata.SetName( 'vectors' )
                md[ 'vectors'] = ','.join( vars ) 
                vtkdata.Modified()
                pointData.SetVectors(vtkdata)
                pointData.SetActiveVectors( 'vectors'  )         
            if len( vars )== 0: raise ModuleError( self, 'No dataset variables selected for output %s.' % orec.name) 
            for varDataId in varDataIds:
                varDataFields = varDataId.split(';')
                dsid = varDataFields[0] 
                varName = varDataFields[1] 
                if varName <> '__zeros__':
                    varDataSpecs = self.getCachedData( varDataId )
                    vmd = varDataSpecs[ 'md' ] 
                    var_md = md[ 'attributes' ]               
#                    vmd[ 'vars' ] = vars               
                    vmd[ 'title' ] = getTitle( dsid, varName, var_md )                 
                    enc_mdata = encodeToString( vmd ) 
                    if enc_mdata: fieldData.AddArray( getStringDataArray( 'metadata:%s' % varName,   [ enc_mdata ]  ) ) 
            if enc_mdata: fieldData.AddArray( getStringDataArray( 'varlist',  vars  ) )                       
            image_data.Modified()
        except Exception, err:
            print>>sys.stderr, "Error encoding variable metadata: %s " % str(err)
            traceback.print_exc()
        return cachedImageDataName


    def getAxisValues( self, axis, roi ):
        values = axis.getValue()
        bounds = None
        if roi:
            if   axis.isLongitude():  bounds = [ roi[0], roi[2] ]
            elif axis.isLatitude():   bounds = [ roi[1], roi[3] ] if ( roi[3] > roi[1] ) else [ roi[3], roi[1] ] 
        if bounds:
            if len( values ) < 2: values = bounds
            else:
                if axis.isLongitude() and (values[0] > values[-1]):
                    values[-1] = values[-1] + 360.0 
                value_bounds = [ min(values[0],values[-1]), max(values[0],values[-1]) ]
                mid_value = ( value_bounds[0] + value_bounds[1] ) / 2.0
                mid_bounds = ( bounds[0] + bounds[1] ) / 2.0
                offset = (360.0 if mid_bounds > mid_value else -360.0)
                trans_val = mid_value + offset
                if (trans_val > bounds[0]) and (trans_val < bounds[1]):
                    value_bounds[0] = value_bounds[0] + offset
                    value_bounds[1] = value_bounds[1] + offset           
                bounds[0] = max( [ bounds[0], value_bounds[0] ] )
                bounds[1] = min( [ bounds[1], value_bounds[1] ] )
        return bounds, values

    def getCoordType( self, axis, outputType ):
        iCoord = -2
        if axis.isLongitude(): 
            self.lon = axis
            iCoord  = 0
        if axis.isLatitude(): 
            self.lat = axis
            iCoord  = 1
        if isLevelAxis( axis ): 
            self.lev = axis
            iCoord  = 2 if ( outputType <> CDMSDataType.Hoffmuller ) else -1
        if axis.isTime():
            self.time = axis
            iCoord  = 2 if ( outputType == CDMSDataType.Hoffmuller ) else -1
        return iCoord

    def getIntersectedRoi( self, var, current_roi ):   
        try:
            newRoi = newList( 4, 0.0 )
            varname = var.outvar.name if hasattr( var,'outvar') else var.name
            tvar = self.cdmsDataset.getTransientVariable( varname )
            if id( tvar ) == id( None ): return current_roi
            current_roi_size = getRoiSize( current_roi )
            for iCoord in range(2):
                axis = None
                if iCoord == 0: axis = tvar.getLongitude()
                if iCoord == 1: axis = tvar.getLatitude()
                axisvals = axis.getValue()          
                if ( len( axisvals.shape) > 1 ):
#                    displayMessage( "Curvilinear grids not currently supported by DV3D.  Please regrid. ")
                    return current_roi
                newRoi[ iCoord ] = axisvals[0] # max( current_roi[iCoord], roiBounds[0] ) if current_roi else roiBounds[0]
                newRoi[ 2+iCoord ] = axisvals[-1] # min( current_roi[2+iCoord], roiBounds[1] ) if current_roi else roiBounds[1]
            if ( current_roi_size == 0 ): return newRoi
            new_roi_size = getRoiSize( newRoi )
            return newRoi if ( ( current_roi_size > new_roi_size ) and ( new_roi_size > 0.0 ) ) else current_roi
        except:
            print>>sys.stderr, "Error getting ROI for input variable"
            traceback.print_exc()
            return current_roi
       
    def getGridSpecs( self, var, roi, zscale, outputType, dset ):   
        dims = var.getAxisIds()
        gridOrigin = newList( 3, 0.0 )
        outputOrigin = newList( 3, 0.0 )
        gridBounds = newList( 6, 0.0 )
        gridSpacing = newList( 3, 1.0 )
        gridExtent = newList( 6, 0 )
        outputExtent = newList( 6, 0 )
        gridShape = newList( 3, 0 )
        gridSize = 1
        domain = var.getDomain()
        self.lev = var.getLevel()
        axis_list = var.getAxisList()
        isCurvilinear = False
        for axis in axis_list:
            size = len( axis )
            iCoord = self.getCoordType( axis, outputType )
            roiBounds, values = self.getAxisValues( axis, roi )
            if iCoord >= 0:
                iCoord2 = 2*iCoord
                gridShape[ iCoord ] = size
                gridSize = gridSize * size
                outputExtent[ iCoord2+1 ] = gridExtent[ iCoord2+1 ] = size-1 
                vmax =  max( values[0], values[-1] )                   
                vmin =  min( values[0], values[-1] )                   
                if iCoord < 2:
                    lonOffset = 0.0 #360.0 if ( ( iCoord == 0 ) and ( roiBounds[0] < -180.0 ) ) else 0.0
                    outputOrigin[ iCoord ] = gridOrigin[ iCoord ] = vmin + lonOffset
                    spacing = (vmax - vmin)/(size-1)
                    if roiBounds:
                        if ( roiBounds[1] < 0.0 ) and  ( roiBounds[0] >= 0.0 ): roiBounds[1] = roiBounds[1] + 360.0
                        gridExtent[ iCoord2 ] = int( round( ( roiBounds[0] - vmin )  / spacing ) )                
                        gridExtent[ iCoord2+1 ] = int( round( ( roiBounds[1] - vmin )  / spacing ) )
                        if gridExtent[ iCoord2 ] > gridExtent[ iCoord2+1 ]:
                            geTmp = gridExtent[ iCoord2+1 ]
                            gridExtent[ iCoord2+1 ] = gridExtent[ iCoord2 ] 
                            gridExtent[ iCoord2 ] = geTmp
                        outputExtent[ iCoord2+1 ] = gridExtent[ iCoord2+1 ] - gridExtent[ iCoord2 ]
                        outputOrigin[ iCoord ] = lonOffset + roiBounds[0]
                    roisize = gridExtent[ iCoord2+1 ] - gridExtent[ iCoord2 ] + 1                  
                    gridSpacing[ iCoord ] = spacing
                    gridBounds[ iCoord2 ] = roiBounds[0] if roiBounds else vmin 
                    gridBounds[ iCoord2+1 ] = (roiBounds[0] + roisize*spacing) if roiBounds else vmax
                else:                                             
                    gridSpacing[ iCoord ] = 1.0
#                    gridSpacing[ iCoord ] = zscale
                    gridBounds[ iCoord2 ] = vmin  # 0.0
                    gridBounds[ iCoord2+1 ] = vmax # float( size-1 )
        if gridBounds[ 2 ] > gridBounds[ 3 ]:
            tmp = gridBounds[ 2 ]
            gridBounds[ 2 ] = gridBounds[ 3 ]
            gridBounds[ 3 ] = tmp
        gridSpecs = {}
        md = { 'datasetId' : self.datasetId,  'bounds':gridBounds, 'lat':self.lat, 'lon':self.lon, 'lev':self.lev, 'time': self.timeAxis }
        gridSpecs['gridOrigin'] = gridOrigin
        gridSpecs['outputOrigin'] = outputOrigin
        gridSpecs['gridBounds'] = gridBounds
        gridSpecs['gridSpacing'] = gridSpacing
        gridSpecs['gridExtent'] = gridExtent
        gridSpecs['outputExtent'] = outputExtent
        gridSpecs['gridShape'] = gridShape
        gridSpecs['gridSize'] = gridSize
        gridSpecs['md'] = md
        if dset:  gridSpecs['attributes'] = dset.dataset.attributes
        return gridSpecs   
                 
    def computeMetadata( self ):
        metadata = PersistentVisualizationModule.computeMetadata( self )
        if self.cdmsDataset:
            metadata[ 'vars2d' ] = self.cdmsDataset.getVariableList( 2 )
            metadata[ 'vars3d' ] = self.cdmsDataset.getVariableList( 3 )
        if self.fileSpecs: metadata[ 'fileSpecs' ] = self.fileSpecs
        if self.varSpecs:  metadata[ 'varSpecs' ]  = self.varSpecs
        if self.gridSpecs: metadata[ 'gridSpecs' ] = self.gridSpecs
        return metadata

class PM_CDMS_ChartDataReader( PM_CDMSDataReader ):

    def __init__(self, mid, **args):
        self.outputType = CDMSDataType.ChartData
        PM_CDMSDataReader.__init__( self, mid, **args)

class CDMS_ChartDataReader(WorkflowModule):
    
    PersistentModuleClass = PM_CDMS_ChartDataReader
    
    def __init__( self, **args ):
        WorkflowModule.__init__(self, **args)     
        
class PM_CDMS_VolumeReader( PM_CDMSDataReader ):

    def __init__(self, mid, **args):
        self.outputType = CDMSDataType.Volume
        PM_CDMSDataReader.__init__( self, mid, **args)

class CDMS_VolumeReader(WorkflowModule):
    
    PersistentModuleClass = PM_CDMS_VolumeReader
    
    def __init__( self, **args ):
        WorkflowModule.__init__(self, **args)     

class PM_CDMS_HoffmullerReader( PM_CDMSDataReader ):

    def __init__(self, mid, **args):
        self.outputType = CDMSDataType.Hoffmuller
        PM_CDMSDataReader.__init__( self, mid, **args)
    
class CDMS_HoffmullerReader(WorkflowModule):
    
    PersistentModuleClass = PM_CDMS_HoffmullerReader
    
    def __init__( self, **args ):
        WorkflowModule.__init__(self, **args)     

class PM_CDMS_SliceReader( PM_CDMSDataReader ):

    def __init__(self, mid, **args):
        self.outputType = CDMSDataType.Slice
        PM_CDMSDataReader.__init__( self, mid, **args)

class CDMS_SliceReader(WorkflowModule):
    
    PersistentModuleClass = PM_CDMS_SliceReader
    
    def __init__( self, **args ):
        WorkflowModule.__init__(self, **args) 
        
        
class PM_CDMS_VectorReader( PM_CDMSDataReader ):

    def __init__(self, mid, **args):
        self.outputType = CDMSDataType.Vector
        PM_CDMSDataReader.__init__( self, mid, **args)

class PM_CDMS_VariableSpaceReader( PM_CDMSDataReader ):

    def __init__(self, mid, **args):
        self.outputType = CDMSDataType.VariableSpace
        PM_CDMSDataReader.__init__( self, mid, **args)


class CDMS_VectorReader(WorkflowModule):
    
    PersistentModuleClass = PM_CDMS_VectorReader
    
    def __init__( self, **args ):
        WorkflowModule.__init__(self, **args) 

class CDMS_VariableSpaceReader(WorkflowModule):
    
    PersistentModuleClass = PM_CDMS_VariableSpaceReader
    
    def __init__( self, **args ):
        WorkflowModule.__init__(self, **args) 

                           
class CDMSReaderConfigurationWidget(DV3DConfigurationWidget): 
    """
    CDMSReaderConfigurationWidget ...
    
    """
    
    def __init__(self, module, controller, outputType, parent=None):
        """ CDMSReaderConfigurationWidget(module: Module,
                                       controller: VistrailController,
                                       parent: QWidget)
                                       -> CDMSReaderConfigurationWidget
        Setup the dialog ...
        
        """
        self.outputType = outputType
        self.outRecMgr = None
        self.refVar = None
        self.levelsAxis = None
        self.serializedPortData = ''
        self.datasetId = None
        DV3DConfigurationWidget.__init__(self, module, controller, 'CDMS Data Reader Configuration', parent)
        self.outRecMgr = OutputRecManager()  
        self.initializeOutput() 
        self.stateChanged( False )     
     
    def getParameters( self, module ):
        global PortDataVersion
        pmod = self.getPersistentModule()
        ( self.variableList, self.datasetId, self.timeRange, self.refVar, self.levelsAxis ) =  DV3DConfigurationWidget.getVariableList( module.id ) 
        portData = pmod.getPortData( dbmod=self.module, datasetId=self.datasetId ) # getFunctionParmStrValues( module, "portData" )
        if portData and portData[0]: 
             self.serializedPortData = portData[0]   
             PortDataVersion = int( portData[1] )    
                                                  
    def createLayout(self):
        """ createEditor() -> None
        Configure sections
        
        """        
        outputsTab = QWidget()        
        self.tabbedWidget.addTab( outputsTab, 'output' ) 
        self.tabbedWidget.setCurrentWidget(outputsTab)
        outputsLayout = QVBoxLayout()                
        outputsTab.setLayout( outputsLayout )
        
        noutLayout = QHBoxLayout()                 
        outputsLayout.addLayout( noutLayout )
                           
        self.outputsTabbedWidget = QTabWidget()
        outputsLayout.addWidget( self.outputsTabbedWidget )
        
    def updateController(self, controller):
        global PortDataVersion
        PortDataVersion = PortDataVersion + 1
        parameterList = [ ('portData', [ self.serializedPortData, PortDataVersion ] ) ]
        self.persistParameterList( parameterList, datasetId=self.datasetId )
        self.stateChanged(False)
           
    def okTriggered(self, checked = False):
        """ okTriggered(checked: bool) -> None
        Update vistrail controller (if neccesssary) then close the widget
        
        """
        self.serializePortData()
        self.updateController(self.controller)
        self.emit(SIGNAL('doneConfigure()'))
#        self.close()
                                       
    def initializeOutput( self ):
        print " initializeOutputs, serializedPortData: %s " % self.serializedPortData
        if self.serializedPortData:
            oRecMgr = OutputRecManager( self.serializedPortData )
            for oRec in oRecMgr.getOutputRecs( self.datasetId ):
                variableSelections = oRec.varList if oRec.varList else []
                self.addOutputTab( oRec.ndim, oRec.name, variableSelections, oRec.level )
                for oRec in self.outRecMgr.getOutputRecs( self.datasetId ): oRec.varSelections = variableSelections
        if   self.outputType == CDMSDataType.Volume:    
            self.addOutputTab( 3, 'volume'  )
        if   self.outputType == CDMSDataType.Hoffmuller:
            self.addOutputTab( 4, 'volume'  )
        elif self.outputType == CDMSDataType.Slice:     
            self.addOutputTab( 2, 'slice' )
        elif self.outputType == CDMSDataType.Vector:    
            self.addOutputTab( 3, 'volume' )
        elif self.outputType == CDMSDataType.ChartData:    
            self.addOutputTab( 3, 'volume' )
        self.updateVariableLists()
                
    def getOutputTabIndex( self, name ):
        ntabs = self.outputsTabbedWidget.count()
        for iTab in range( ntabs ):
            tabName = str( self.outputsTabbedWidget.tabText( iTab ) )
            if tabName == name: return iTab # self.outputsTabbedWidget.widget(iTab)
        return -1
               
    def addOutputTab( self, ndim, output_name = None, variableSelections=[], level=None ): 
        if output_name == None:
            qtname, ok = QInputDialog.getText( self, 'Get Output Name', 'Output name:' )
            if ok: output_name = str(qtname).strip().replace( ' ', '_' ).translate( None, OutputRecManager.sep )
        if output_name <> None:
            iExistingTabIndex = self.getOutputTabIndex( output_name )
            if iExistingTabIndex < 0:
                outputTab = self.createOutputTab( ndim, output_name, variableSelections, level )  
                if outputTab <> None:
                    self.outputsTabbedWidget.addTab( outputTab, output_name ) 
                    self.outputsTabbedWidget.setCurrentWidget( outputTab )
                    return outputTab
        return None, None
        
    def removeOutputTab( self ):
        tabIndex = self.outputsTabbedWidget.currentIndex()
        outputName = str( self.outputsTabbedWidget.tabText(tabIndex) )
        self.outRecMgr.deleteOutput( self.datasetId, outputName )
        self.outputsTabbedWidget.removeTab( tabIndex )
        self.updatePorts()

#    def updateNOutouts( self, nout_str ):
#        noutputs = int( nout_str )
#        current_nout = len( self.outputRecs )
#        if noutputs > current_nout:
#            for iout in range( current_nout, noutputs ):
#                default_name = "data%d" % iout
                    
    def createOutputTab( self, ndim, name, variableSelections = [], level=None ):  
        otab = QWidget()  
        otabLayout = QVBoxLayout()                
        otab.setLayout( otabLayout )

        if self.outputType == CDMSDataType.ChartData:
            varsComboList = []
            nvars = 3
            
            for iVar in range(nvars):           
                variables_Layout = QHBoxLayout()      
                variables_label = QLabel( "Select Output Variable %d:" % iVar )
                variables_Layout.addWidget( variables_label ) 
                varsCombo =  QComboBox ( self )
                self.connect( varsCombo, SIGNAL("currentIndexChanged(QString)"), self.selectedVariableChanged ) 
                variables_label.setBuddy( varsCombo )
                variables_Layout.addWidget( varsCombo )  
                otabLayout.addLayout( variables_Layout )
                varsComboList.append( varsCombo )
                               
            orec = OutputRec( name, ndim=ndim, varComboList=varsComboList, varSelections=variableSelections )
            self.outRecMgr.addOutputRec( self.datasetId, orec )            
        elif self.outputType == CDMSDataType.Vector:
            varsComboList = []
            for vector_component in [ 'x', 'y', 'z' ]:
                variables_Layout = QHBoxLayout()      
                variables_label = QLabel( "Select %s component:" % vector_component )
                variables_Layout.addWidget( variables_label ) 
                varsCombo =  QComboBox ( self )
                self.connect( varsCombo, SIGNAL("currentIndexChanged(QString)"), self.selectedVariableChanged ) 
                variables_label.setBuddy( varsCombo )
                varsCombo.setMaximumHeight( 30 )
                variables_Layout.addWidget( varsCombo )  
                otabLayout.addLayout( variables_Layout )
                varsComboList.append( varsCombo )                  
            orec = OutputRec( name, ndim=ndim, varComboList=varsComboList, varSelections=variableSelections ) 
            self.outRecMgr.addOutputRec( self.datasetId, orec )            
        elif self.outputType == CDMSDataType.Hoffmuller:
            levels_Layout = QHBoxLayout() 
            
            levels_label = QLabel( "Select Level:"  )
            levels_Layout.addWidget( levels_label ) 
            levelsCombo =  QComboBox ( self )
            self.connect( levelsCombo, SIGNAL("currentIndexChanged(QString)"), self.selectedLevelChanged ) 
            levels_label.setBuddy( levelsCombo )
            levels_Layout.addWidget( levelsCombo )  
            otabLayout.addLayout( levels_Layout )
             
            variables_Layout = QHBoxLayout()     
            variables_label = QLabel( "Select Output Variable:"  )
            variables_Layout.addWidget( variables_label ) 
            varsCombo =  QComboBox ( self )
            self.connect( varsCombo, SIGNAL("currentIndexChanged(QString)"), self.selectedVariableChanged ) 
            variables_label.setBuddy( varsCombo )
            variables_Layout.addWidget( varsCombo )  
            otabLayout.addLayout( variables_Layout )
                    
            orec = OutputRec( name, ndim=ndim, varComboList=[varsCombo], levelsCombo=levelsCombo, varSelections=variableSelections, level=level ) 
            self.outRecMgr.addOutputRec( self.datasetId, orec ) 
        else:
            variables_Layout = QHBoxLayout()      
            variables_label = QLabel( "Select Output Variable:"  )
            variables_Layout.addWidget( variables_label ) 
            varsCombo =  QComboBox ( self )
            self.connect( varsCombo, SIGNAL("currentIndexChanged(QString)"), self.selectedVariableChanged ) 
            variables_label.setBuddy( varsCombo )
            variables_Layout.addWidget( varsCombo )  
            otabLayout.addLayout( variables_Layout )
                    
            orec = OutputRec( name, ndim=ndim, varComboList=[varsCombo], varSelections=variableSelections ) 
            self.outRecMgr.addOutputRec( self.datasetId, orec ) 
        
        return otab
    
    def selectedVariableChanged(self, vname ):
        self.stateChanged()
        
    def selectedLevelChanged(self, vname ):
        self.stateChanged()
    
    def updateVariableLists(self):
        if self.outRecMgr:  
            for oRec in self.outRecMgr.getOutputRecs( self.datasetId ): 
                for varCombo in oRec.varComboList: 
                    varCombo.clear()
                    if ( self.outputType == CDMSDataType.Vector ):  
                        varCombo.addItem( '__zeros__' ) 
                    if ( oRec.levelsCombo <> None) and ( self.levelsAxis <> None ): 
                        oRec.levelsCombo.clear()
                        levels = self.levelsAxis.getValue()
                        for level in levels: 
                            oRec.levelsCombo.addItem( QString( str(level) ) )                     
            for ( var, var_ndim ) in self.variableList:               
                for oRec in self.outRecMgr.getOutputRecs( self.datasetId ):
                    if (var_ndim == oRec.ndim) or ( (oRec.ndim == 4) and (var_ndim > 1) ) : 
                        for varCombo in oRec.varComboList: varCombo.addItem( str(var) ) 
                    
            for oRec in self.outRecMgr.getOutputRecs( self.datasetId ): 
                if oRec.varSelections:
                    varIter = iter( oRec.varSelections )
                    for varCombo in oRec.varComboList: 
                        try:
                            varSelectionRec = varIter.next()
                            itemIndex = varCombo.findText( varSelectionRec[0], Qt.MatchFixedString )
                            if itemIndex >= 0: varCombo.setCurrentIndex( itemIndex )
                        except: pass
                if oRec.level:
                    itemIndex = oRec.levelsCombo.findText(  oRec.level, Qt.MatchFixedString )
                    oRec.levelsCombo.setCurrentIndex( itemIndex )
        
    def getCurentOutputRec(self):
        tabIndex = self.outputsTabbedWidget.currentIndex()
        outputName = str( self.outputsTabbedWidget.tabText(tabIndex) )
        return self.outRecMgr.getOutputRec( self.datasetId, outputName ) 
        
    def serializePortData( self ):
        oRec = self.getCurentOutputRec()
        if oRec: oRec.updateSelections()
        self.serializedPortData = self.outRecMgr.serialize()
        print " -- PortData: %s " % self.serializedPortData


class CDMS_HoffmullerReaderConfigurationWidget(CDMSReaderConfigurationWidget):

    def __init__(self, module, controller, parent=None):
        CDMSReaderConfigurationWidget.__init__(self, module, controller, CDMSDataType.Hoffmuller, parent)

    def getParameters( self, module ):
        CDMSReaderConfigurationWidget.getParameters( self, module ) 

class CDMS_ChartDataConfigurationWidget(CDMSReaderConfigurationWidget):

    def __init__(self, module, controller, parent=None):
        CDMSReaderConfigurationWidget.__init__(self, module, controller, CDMSDataType.ChartData, parent)

    def getParameters( self, module ):
        CDMSReaderConfigurationWidget.getParameters( self, module ) 

class CDMS_VolumeReaderConfigurationWidget(CDMSReaderConfigurationWidget):

    def __init__(self, module, controller, parent=None):
        CDMSReaderConfigurationWidget.__init__(self, module, controller, CDMSDataType.Volume, parent)

    def getParameters( self, module ):
        CDMSReaderConfigurationWidget.getParameters( self, module ) 

class CDMS_SliceReaderConfigurationWidget(CDMSReaderConfigurationWidget):

    def __init__(self, module, controller, parent=None):
        CDMSReaderConfigurationWidget.__init__(self, module, controller, CDMSDataType.Slice, parent)


class CDMS_VectorReaderConfigurationWidget(CDMSReaderConfigurationWidget):

    def __init__(self, module, controller, parent=None):
        CDMSReaderConfigurationWidget.__init__(self, module, controller, CDMSDataType.Vector, parent)

if __name__ == '__main__':
    dataFilePath = '/Developer/Data/AConaty/comp-ECMWF/ac-comp1-geos5.xml'
    dataset = cdms2.open( dataFilePath )
    var = dataset[ 'tmpu' ]
    pass
    

