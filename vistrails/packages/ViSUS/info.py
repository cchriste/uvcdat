identifier = 'org.pascucci.visus'
version = '0.0.2'
name = "ViSUS"

def package_dependencies():
    import core.packagemanager
    dependencies = []
    manager = core.packagemanager.get_package_manager()
    if manager.has_package('edu.utah.sci.vistrails.spreadsheet'):
      dependencies.append('edu.utah.sci.vistrails.spreadsheet')
    dependencies.append('gov.llnl.uvcdat')
    dependencies.append('gov.llnl.uvcdat.cdms')
    return dependencies

def package_requirements():
    import core.requirements
    if not core.requirements.python_module_exists('visuspy'):
      raise core.requirements.MissingRequirement('visuspy')
    if not core.requirements.python_module_exists('PyQt4'):
      from core import debug
      debug.warning('PyQt4 is not available. There will be no interaction '
                    'between ViSUS and the spreadsheet.')
    import visuspy

