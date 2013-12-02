from packages.uvcdat.init import Variable, Plot
from packages.uvcdat_cdms.init import CDMSVariable
from packages.uvcdat.init import expand_port_specs as _expand_port_specs
from core.uvcdat.plot_pipeline_helper import PlotPipelineHelper
from packages.uvcdat_cdms.pipeline_helper import CDMSPipelineHelper, CDMSPlotWidget

from core.uvcdat.plot_registry import get_plot_registry
from core.modules.module_registry import get_module_registry
from core.modules.vistrails_module import Module
from core.uvcdat.plotmanager import get_plot_manager
from packages.spreadsheet.basic_widgets import CellLocation, SpreadsheetCell

import core.db.action
import core.db.io
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import pyqtSlot, pyqtSignal
from packages.uvcdat_cdms.init import CDMSPlot, CDMSVariable, CDMSCell, CDMSVariableOperation, \
       CDMSUnaryVariableOperation, CDMSBinaryVariableOperation, \
       CDMSNaryVariableOperation
from gui.uvcdat.uvcdatCommons import plotTypes
import api

import visuscell


class VisusPipelineHelper(PlotPipelineHelper):

    @staticmethod
    def show_configuration_widget(controller, version, plot_obj=None):
        pipeline = controller.vt_controller.vistrail.getPipeline(version)
        cell = CDMSPipelineHelper.find_modules_by_type(pipeline,[visuscell.VisusCell])
        vars = CDMSPipelineHelper.find_modules_by_type(pipeline,
                                                       [CDMSVariable,
                                                        CDMSVariableOperation])
        if len(cell) == 0:
            return visuscell.VisusCellConfigurationWidget(None,controller)
        else:
            vcell = cell[0].module_descriptor.module()
            return visuscell.VisusCellConfigurationWidget(cell[0],controller)

    @staticmethod
    def build_plot_pipeline_action(controller, version, var_modules, plots,row, col):
        plot_type = plots[0].parent
        plot_gm = plots[0].name

        if controller is None:
            controller = api.get_current_controller()
            version = 0L

        reg = get_module_registry()
        ops = []
        cell_module = None

        pipeline = controller.vistrail.getPipeline(version)

        var_module = var_modules[0]

        try:
            temp_var_module = pipeline.get_module_by_id(var_module.id)
        except KeyError:
            temp_var_module = None

        if temp_var_module is not None:
            var_module = temp_var_module
        else:
            ops.append(('add',var_module))

        for plot in plots:

            plot_type = plot.parent
            plot_gm = plot.name

            import re
            plotname = re.sub(r'\s', '', plot_gm)

            plot_module = PlotPipelineHelper.find_module_by_name(pipeline, plotname)
            if plot_module is not None:
                continue

            plot_descriptor = reg.get_descriptor_by_name('org.pascucci.visus', 'VisusCell')
            plot_module = controller.create_module_from_descriptor(plot_descriptor)

            ops.append(('add',plot_module))

            if cell_module is None:
                cell_module = plot_module

                if issubclass(var_modules[0].module_descriptor.module, CDMSVariable):
                    conn = controller.create_connection(var_module, 'self',
                                                        plot_module, 'variable')
                else:
                    conn = controller.create_connection(var_module, 'self',
                                                        cell_module, 'variable')
                ops.append(('add', conn))

                loc_module = controller.create_module_from_descriptor(
                    reg.get_descriptor_by_name('edu.utah.sci.vistrails.spreadsheet',
                                               'CellLocation'))
                functions = controller.create_functions(loc_module,
                    [('Row', [str(row+1)]), ('Column', [str(col+1)])])
                for f in functions:
                    loc_module.add_function(f)

                loc_conn = controller.create_connection(loc_module, 'self',
                                                        cell_module, 'Location')
                ops.extend([('add', loc_module),
                            ('add', loc_conn)])

        action = core.db.action.create_action(ops)
        controller.change_selected_version(version)
        controller.add_new_action(action)
        controller.perform_action(action)
        return action

    @staticmethod
    def find_plot_modules(pipeline):
        res = []
        return res


    @staticmethod
    def load_pipeline_in_location(pipeline, controller, sheetName, row, col,plot_type, cell):
        pass

    @staticmethod
    def build_python_script_from_pipeline(controller, version, plot=None):
        return "unsupported operation"

    @staticmethod
    def copy_pipeline_to_other_location(pipeline, controller, sheetName, row, col,plot_type, cell):
        return None
