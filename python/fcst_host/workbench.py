# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD workbench entry points; commands dispatch to canonical operations."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import uuid

from fcst_contracts import read
from .controller import Session
from . import review

SESSIONS = {}


def current():
    import FreeCAD as App
    session = SESSIONS.get(App.ActiveDocument.Name if App.ActiveDocument else '')
    return session if session and not session.closed else None


class Selection:
    def addSelection(self, document, obj_name, sub, point):
        import FreeCAD as App
        session = current()
        if session and session.panel:
            obj=App.getDocument(document).getObject(obj_name)
            if hasattr(obj,'FCSTEntityId') and session.panel.selected != obj.FCSTEntityId:
                session.panel.select_entity(obj.FCSTEntityId)


SELECTION = Selection()


def show(session):
    import FreeCADGui as Gui
    from PySide6 import QtCore
    from .widgets import ReviewPanel
    SESSIONS[session.doc.Name]=session
    panel=ReviewPanel(session,Gui.getMainWindow())
    Gui.getMainWindow().addDockWidget(QtCore.Qt.RightDockWidgetArea,panel)
    panel.show()
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    return panel


def template(kind, model):
    templates=json.loads(Path(__file__).with_name('templates.json').read_bytes())
    entity=deepcopy(templates[kind]); entity['id']=str(uuid.uuid4()); entity['label']='New '+kind.title()
    # Resolve template references by their declared synthetic target kind.
    references={'submodel_id':'submodel','node_id':'node','sensor_node_id':'node',
        'from_node_id':'node','to_node_id':'node','frame_id':'frame','geometry_id':'geometry',
        'mesh_id':'mesh','material_id':'material','optics_id':'optics','load_id':'load',
        'environment_id':'environment','facet_ids':'facet','load_ids':'load','control_ids':'control'}
    def remap(value, key=''):
        if isinstance(value,dict): return {k:remap(v,k) for k,v in value.items()}
        if isinstance(value,list): return [remap(v,key) for v in value]
        if isinstance(value,str) and (key.endswith('_id') or key.endswith('_ids')):
            wanted=references.get(key)
            matches=[e['id'] for e in model['entities'] if e['kind']==wanted]
            match=matches[min(1,len(matches)-1)] if matches and key=='to_node_id' else matches[0] if matches else None
            return match or value
        return value
    # Stable user identity must not be remapped to an existing entity.
    entity=remap(entity)
    if kind=='load': entity.pop('expression_id',None)
    if kind=='case': entity.update(load_ids=[],control_ids=[],overlays=[])
    if kind=='node': entity.update(classification='capacitive',temperature=dict(value=300,unit='K'),capacity=dict(value=1,unit='J/K'))
    if kind=='material': entity.pop('frame_id',None); entity.pop('conductivity_tensor',None)
    return entity


class Command:
    def __init__(self,name,action,active=True):
        self.name,self.action,self.active=name,action,active

    def GetResources(self):
        return dict(MenuText=self.name,ToolTip=self.name)

    def IsActive(self):
        return not self.active or current() is not None

    def Activated(self):
        import FreeCADGui as Gui
        from .widgets import diagnostic
        try: self.action()
        except (ValueError,OSError) as error:
            session=current()
            if session and session.panel: session.panel.status.setText(diagnostic(error))
            else: Gui.getMainWindow().statusBar().showMessage(diagnostic(error))


def create(example=False):
    return show(Session.create(Path(tempfile.mkdtemp(prefix='fcst-host-')),
                              review.example_model() if example else review.new_model()))


def open_project():
    from PySide6 import QtWidgets
    path,_=QtWidgets.QFileDialog.getOpenFileName(None,'Open FCST project','','FCST project (*.fcst)')
    if path: show(Session.open(path,Path(tempfile.mkdtemp(prefix='fcst-host-'))))


def save_project():
    from PySide6 import QtWidgets
    path,_=QtWidgets.QFileDialog.getSaveFileName(None,'Save coordinated FCST project','','FCST project (*.fcst)')
    if path:
        path=Path(path).with_suffix('.fcst')
        current().save(path.with_suffix('.FCStd'),path)
        current().panel.status.setText('Saved • host and portable project synchronized')


def add_entity(kind):
    from .widgets import EntityEditor
    from PySide6 import QtCore
    session=current()
    dialog=EntityEditor(session,template(kind,session.store.snapshot()),session.panel)
    dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose); dialog.show()


def capture_surface():
    import FreeCADGui as Gui
    selected=Gui.Selection.getSelectionEx()
    if len(selected)!=1 or len(selected[0].SubElementNames)!=1:
        from fcst_app.persistence import reject
        reject('select_one_face')
    current().capture_surface(selected[0].Object,selected[0].SubElementNames[0])
    current().panel.refresh()


def open_field():
    from PySide6 import QtWidgets
    from .spatial import SpatialView
    from fcst_contracts import loads
    path,_=QtWidgets.QFileDialog.getOpenFileName(None,'Open canonical spatial field','','Spatial descriptor (*.json)')
    if path:
        value=read('spatial',loads(Path(path).read_bytes()))
        session=current();session.import_field(value)
        session.panel.time.setRange(0,len(value['times'])-1);session.panel.time.setEnabled(True)
        session.panel.render_spatial()


def bind_selection():
    import FreeCADGui as Gui
    from fcst_app.persistence import reject
    session=current()
    selected=[s for s in Gui.Selection.getSelectionEx() if s.SubElementNames]
    if not session.panel.selected or len(selected)!=1 or len(selected[0].SubElementNames)!=1:
        reject('select_entity_and_one_face')
    session.bind(session.panel.selected,selected[0].Object,selected[0].SubElementNames[0])
    session.panel.refresh()


def register():
    import FreeCADGui as Gui
    if 'FCSTWorkbench' in Gui.listWorkbenches(): return
    for name,title,action,active in (
        ('New','New thermal model',create,False),
        ('Example','Open analytic network',lambda:create(True),False),
        ('Open','Open project',open_project,False),
        ('Save','Save project',save_project,True),
        ('Undo','Undo thermal edit',lambda:current().panel.undo(),True),
        ('Reconcile','Rebuild host from project',lambda:(current().reconcile(),current().panel.refresh()),True),
        ('Settings','Solver settings',lambda:current().panel.edit_settings(),True),
        ('Surface','Capture selected CAD face',capture_surface,True),
        ('Field','Open canonical spatial field',open_field,True),
        ('Bind','Link selected entity to CAD face',bind_selection,True),
        ('Solve','Solve thermal model',lambda:current().panel.solve(),True)):
        Gui.addCommand('FCST_'+name,Command(title,action,active))
    for kind in ('submodel','node','face','facet','material','optics','conductor','load','environment','case','frame','control'):
        Gui.addCommand('FCST_Add_'+kind,Command('Add '+kind.title(),lambda k=kind:add_entity(k)))

    class FCSTWorkbench(Gui.Workbench):
        MenuText='FCST Thermal'; ToolTip='Spacecraft thermal modeling and result review'

        def Initialize(self):
            commands=['FCST_'+n for n in ('New','Example','Open','Save','Undo','Reconcile','Surface','Bind','Field','Settings','Solve')]
            self.appendToolbar('FCST Thermal',commands)
            self.appendMenu('FCST Thermal',commands)
            self.appendMenu(['FCST Thermal','Create'],['FCST_Add_'+k for k in ('submodel','node','face','facet','material','optics','conductor','load','environment','case','frame','control')])

        def Activated(self):
            Gui.Selection.addObserver(SELECTION)
            session=current()
            if session and session.panel: session.panel.show()

        def Deactivated(self):
            Gui.Selection.removeObserver(SELECTION)

        def GetClassName(self):
            return 'Gui::PythonWorkbench'

    Gui.addWorkbench(FCSTWorkbench())
