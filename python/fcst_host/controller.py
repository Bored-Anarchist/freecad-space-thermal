# SPDX-License-Identifier: LGPL-2.1-or-later
"""Application-thread host projection; the portable project remains authoritative."""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import uuid

from fcst_app.fem_adapter import assert_thread
from fcst_app.persistence import Package, encode, reject, semantic_hash
from fcst_app.store import ProjectStore
from . import review


def shape_signature(shape):
    """Stable geometric signature across BREP reopen, in host millimetres.

    Twelve significant digits remove serializer roundoff. Face/edge ordering,
    orientation, vertices and geometric moments stay explicit; source revisions
    and dirty-state guards independently prevent implicit topology reassignment.
    """
    def vector(value): return [format(float(x),'.12g') for x in value]
    data=dict(version=1,kind=shape.ShapeType,orientation=shape.Orientation,
        vertices=[vector(v.Point) for v in shape.Vertexes],
        edges=[format(e.Length,'.12g') for e in shape.Edges],
        faces=[dict(area=format(f.Area,'.12g'),center=vector(f.CenterOfMass),orientation=f.Orientation) for f in shape.Faces])
    return sha256(encode(data)).hexdigest()


class Observer:
    def __init__(self, session):
        self.session = session

    def changed(self, doc):
        s = self.session
        if not s.closed and not s.projecting and doc == s.doc:
            s.diverged = True
            s.store.mark_host_dirty()
            s.clear_display()
            if s.on_change:
                s.on_change()

    def slotChangedObject(self, obj, prop):
        # View properties and recomputation are presentation, not engineering edits.
        if prop not in ('Visibility', 'Label', 'Label2', 'ShapeColor', 'LineColor'):
            self.changed(obj.Document)

    def slotCreatedObject(self, obj):
        self.changed(obj.Document)

    def slotDeletedObject(self, obj):
        self.changed(obj.Document)

    def slotUndoDocument(self, doc):
        self.changed(doc)

    def slotRedoDocument(self, doc):
        self.changed(doc)

    def slotDeletedDocument(self, doc):
        if doc == self.session.doc:
            self.session.close()

    def slotActivateDocument(self, doc):
        if self.session.panel:
            self.session.panel.setVisible(doc==self.session.doc)


class ViewProvider:
    def __init__(self, view):
        view.Proxy = self

    def attach(self, view):
        self.view = view

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return 'Flat Lines'

    def onChanged(self, view, prop):
        pass

    def updateData(self, obj, prop):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


class Session:
    def __init__(self, doc, store, workspace):
        import FreeCAD as App
        assert_thread()
        self.doc, self.store, self.workspace = doc, store, Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.projecting, self.closed, self.on_change = False, False, None
        self.diverged = False
        self.spatial_view, self.spatial_id = None, None
        self.result_id, self.result, self.panel, self.job = None, None, None, None
        self.options = deepcopy(review.DEFAULT_SETTINGS)
        self.case_id = None
        self.bindings = {}
        self.observer = Observer(self)
        self.project()
        App.addDocumentObserver(self.observer)

    @classmethod
    def create(cls, workspace, model=None):
        import FreeCAD as App
        workspace = Path(workspace); workspace.mkdir(parents=True, exist_ok=True)
        store = ProjectStore.create(workspace/'project.db', model or review.new_model())
        return cls(App.newDocument('FCST'), store, workspace)

    @classmethod
    def open(cls, package_path, workspace):
        import FreeCAD as App
        workspace = Path(workspace); workspace.mkdir(parents=True, exist_ok=True)
        store = ProjectStore.create(workspace/'project.db', package=Package.open(package_path))
        doc=App.newDocument('FCST')
        session=None
        try:
            session=cls(doc,store,workspace)
            return session.restore()
        except BaseException:
            if session is not None:session.close()
            else:store.close()
            App.closeDocument(doc.Name)
            raise

    def restore(self):
        session,store=self,self.store
        configurations=[]
        for artifact in store._artifacts():
            if artifact[2].startswith('review-settings/'):
                from fcst_contracts import loads
                configurations.append(review.configuration(loads(artifact[3]),store.snapshot()))
        if configurations:
            configuration=max(configurations,key=lambda c:c['sequence'])
            session.options=review.settings(configuration['options'])
            session.case_id=configuration['case_id']
            session.spatial_id=configuration.get('spatial_id')
            for binding in configuration.get('bindings',[]):
                target=session.objects.get(binding['target_id'])
                if target is None or shape_signature(target.Shape)!=binding['source_revision']:
                    reject('attachment_reassignment_required')
                session.bind(binding['entity_id'],target,binding['subelement'])
        for artifact in store._artifacts():
            if artifact[2].startswith('review-fields/'):
                if session.spatial_id is not None and artifact[0]!=session.spatial_id:continue
                from fcst_contracts import loads
                value=loads(artifact[3])
                if value.get('model_hash')==semantic_hash(store.snapshot()):
                    from .spatial import SpatialView
                    session.spatial_view=SpatialView(session,value)
                    session.spatial_id=artifact[0]
                    break
        if session.spatial_id is not None and session.spatial_view is None:reject('review_configuration')
        # Portable projection is rebuilt. No package-supplied Python or host path runs.
        candidates = [d for d in store.state()['derived'] if d['kind'] == 'solve' and not d['stale']]
        for item in reversed(candidates):
            try:
                session.load_result(item['id'])
                break
            except ValueError:
                continue
        return session

    @contextmanager
    def projection(self):
        assert_thread()
        previous = self.projecting
        self.projecting = True
        try:
            yield
        finally:
            self.projecting = previous

    def project(self):
        import FreeCAD as App
        import Part
        import ObjectsFem
        assert_thread()
        with self.projection():
            model = self.store.snapshot()
            root = self.doc.getObject('FCSTAnalysis')
            if root is None:
                root = ObjectsFem.makeAnalysis(self.doc, 'FCSTAnalysis')
                root.Label = 'FCST Thermal Model'
                for name in ('ProjectId', 'ModelHash', 'Revision'):
                    root.addProperty('App::PropertyString', 'FCST'+name, 'FCST')
            root.FCSTProjectId, root.FCSTModelHash = model['project_id'], semantic_hash(model)
            root.FCSTRevision = str(model['revision'])
            self.root = root
            desired = {e['id'] for e in model['entities']}
            for obj in list(self.doc.Objects):
                if hasattr(obj, 'FCSTEntityId') and obj.FCSTEntityId not in desired:
                    self.doc.removeObject(obj.Name)
            nodes = [e for e in model['entities'] if e['kind'] == 'node']
            self.objects = {}
            for entity in model['entities']:
                name = 'FCST_'+entity['id'].replace('-', '')
                obj = self.doc.getObject(name)
                if obj is None:
                    obj = ObjectsFem.makeMaterialSolid(self.doc,name) if entity['kind']=='material' else self.doc.addObject('PartDesign::Feature' if entity['kind'] in ('node', 'conductor', 'geometry', 'face') else 'App::FeaturePython', name)
                    for prop in ('EntityId', 'Kind', 'Data', 'AttachmentState'):
                        obj.addProperty('App::PropertyString', 'FCST'+prop, 'FCST')
                    obj.addProperty('App::PropertyLinkSub', 'FCSTAttachment', 'FCST')
                    obj.addProperty('App::PropertyString', 'FCSTAttachmentSignature', 'FCST')
                    obj.addProperty('App::PropertyString', 'FCSTSourceRevision', 'FCST')
                    root.addObject(obj)
                    if hasattr(obj, 'ViewObject') and obj.ViewObject is not None and entity['kind'] not in ('node', 'conductor', 'geometry', 'face','material'):
                        ViewProvider(obj.ViewObject)
                obj.Label = entity.get('label') or entity['kind'].title()+' '+entity['id'][-8:]
                obj.FCSTEntityId, obj.FCSTKind, obj.FCSTData = entity['id'], entity['kind'], encode(entity).decode()
                obj.FCSTAttachmentState = 'assigned' if obj.FCSTAttachment else 'unassigned' if entity['kind'] in ('face','facet','element') else 'network' if entity['kind']=='node' else 'contact link' if entity['kind']=='conductor' else 'definition'
                for prop in ('FCSTEntityId', 'FCSTKind', 'FCSTData'):
                    obj.setEditorMode(prop, 1)
                self.objects[entity['id']] = obj
                if entity['kind']=='material':
                    from fcst_contracts import normalize
                    material=normalize(entity)
                    obj.Material={'Name':entity.get('label') or 'FCST material',
                        'Density':str(material['density']['value'])+' kg/m^3',
                        'SpecificHeat':str(material['specific_heat']['value'])+' J/kg/K',
                        'ThermalConductivity':str(material['conductivity']['value'])+' W/m/K'}
            from fcst_contracts import normalize
            frames={e['id']:normalize(e) for e in model['entities'] if e['kind']=='frame'}
            local_shapes={}
            for entity in sorted(model['entities'],key=lambda e: 0 if e['kind']=='geometry' else 1):
                obj = self.objects[entity['id']]
                if entity['kind'] == 'geometry':
                    ref = entity['artifact']
                    raw = next(a[3] for a in self.store._artifacts() if a[2] == ref['path'])
                    shape = Part.Shape(); shape.importBrepFromString(raw.decode('utf-8'))
                    local_shapes[entity['id']]=shape.copy()
                    frame=frames[entity['frame_id']];matrix=App.Matrix()
                    for i in range(3):
                        for j in range(3):setattr(matrix,'A'+str(i+1)+str(j+1),frame['rotation'][i][j])
                        setattr(matrix,'A'+str(i+1)+'4',frame['origin'][i]['value']*1000)
                    shape.Placement=App.Placement(matrix).multiply(shape.Placement)
                    obj.Shape = shape
                elif entity['kind'] == 'face':
                    geometry = self.objects[entity['geometry_id']]
                    try:
                        local_face=local_shapes[entity['geometry_id']].getElement(entity['persistent_ref'])
                        if shape_signature(local_face) != entity['signature']:
                            raise ValueError('face_signature')
                        face=geometry.Shape.getElement(entity['persistent_ref'])
                        obj.Shape = face
                        obj.ViewObject.Visibility=False
                        obj.FCSTAttachment = (geometry,[entity['persistent_ref']])
                        obj.FCSTAttachmentSignature = shape_signature(face)
                        obj.FCSTSourceRevision = shape_signature(geometry.Shape)
                        obj.FCSTAttachmentState = 'assigned'
                    except (ValueError,RuntimeError):
                        obj.FCSTAttachmentState = 'invalid / reassign'
            # Abstract network layout is display-only; it is never exported as CAD.
            for index, node in enumerate(nodes):
                obj = self.objects[node['id']]
                obj.Shape = Part.makeSphere(3, App.Vector((index % 8)*30, (index//8)*30, 0))
                obj.ViewObject.ShapeColor = (.32,.65,.72)
            for entity in model['entities']:
                if entity['kind'] == 'conductor':
                    a, b = (self.objects[entity[k]].Shape.BoundBox.Center for k in ('from_node_id', 'to_node_id'))
                    if (a-b).Length > 0:
                        obj = self.objects[entity['id']]
                        obj.Shape = Part.makeLine(a, b)
                        obj.ViewObject.LineColor = (.38,.48,.55)
                        obj.ViewObject.LineWidth = 3
            self.doc.recompute()
        self.check_bindings()
        self.draw_bindings()

    def draw_bindings(self):
        import Part
        with self.projection():
            active=set()
            for key,obj in self.objects.items():
                if obj.FCSTKind!='node' or not obj.FCSTAttachment:continue
                target,names=obj.FCSTAttachment
                try:
                    a,b=obj.Shape.BoundBox.Center,target.Shape.getElement(names[0]).CenterOfMass
                    if (a-b).Length==0:continue
                    name='FCSTMapping_'+key.replace('-','');active.add(name)
                    line=self.doc.getObject(name)
                    if line is None:
                        line=self.doc.addObject('PartDesign::Feature',name)
                        line.addProperty('App::PropertyString','FCSTReviewOverlay','FCST');line.FCSTReviewOverlay='mapping'
                        self.root.addObject(line)
                    line.Shape=Part.makeLine(a,b);line.Label='Review mapping '+key[-8:]
                    line.ViewObject.LineWidth=2;line.ViewObject.LineColor=(.2,.7,.65) if obj.FCSTAttachmentState=='assigned' else (.9,.2,.1)
                except (RuntimeError,ReferenceError,AttributeError,IndexError):continue
            for obj in list(self.doc.Objects):
                if hasattr(obj,'FCSTReviewOverlay') and obj.Name not in active:self.doc.removeObject(obj.Name)

    def edit(self, entity, *, expected_revision=None):
        assert_thread()
        if self.diverged or self.root.FCSTModelHash != semantic_hash(self.store.snapshot()):
            reject('host_reconciliation_required')
        self.store.mark_host_dirty()
        revision = self.store.snapshot()['revision'] if expected_revision is None else expected_revision
        outcome = review.change(self.store, entity, expected_revision=revision)
        self.clear_display()
        with self.projection():
            self.doc.openTransaction('FCST edit')
            try:
                self.project()
                self.doc.commitTransaction()
            except BaseException:
                self.doc.abortTransaction()
                raise
        return outcome

    def undo(self):
        assert_thread()
        state = self.store.state()
        if not state['history']:
            reject('unknown_revision')
        outcome = self.store.apply('local-workbench', {'changes.undo'}, state['model']['project_id'],
            state['model']['revision'], str(uuid.uuid4()), {'revision': state['history'][-1]['revision']}, operation='changes.undo')
        self.store.mark_host_dirty()
        self.clear_display()
        self.project()
        return outcome

    def reconcile(self):
        # Direct host edits have no authority to overwrite canonical values.
        self.clear_display()
        self.project()
        self.diverged = False
        self.store.mark_host_dirty()

    def save(self, host_path, package_path, *, fault=None):
        assert_thread()
        if self.diverged or self.root.FCSTModelHash != semantic_hash(self.store.snapshot()):
            reject('host_reconciliation_required')
        for obj in self.objects.values():
            if obj.FCSTData != encode(next(e for e in self.store.snapshot()['entities'] if e['id']==obj.FCSTEntityId)).decode():
                reject('host_reconciliation_required')
        with self.projection():
            sequence=sum(a[2].startswith('review-settings/') for a in self.store._artifacts())
            artifact_id=str(uuid.uuid4())
            bindings=[]
            for key,obj in self.objects.items():
                if obj.FCSTAttachment:
                    target,names=obj.FCSTAttachment
                    if hasattr(target,'FCSTEntityId') and len(names)==1:
                        bindings.append(dict(entity_id=key,target_id=target.FCSTEntityId,
                            subelement=names[0],source_revision=obj.FCSTSourceRevision))
            self.store.add_artifact(artifact_id,'evidence','review-settings/'+artifact_id+'.json',
                encode(dict(sequence=sequence,options=self.options,case_id=self.case_id,bindings=bindings,spatial_id=self.spatial_id)),
                expected_revision=self.store.snapshot()['revision'])
            staging = self.workspace/('save-'+uuid.uuid4().hex+'.FCStd')
            self.doc.recompute()
            self.doc.saveAs(str(staging))
            return self.store.synchronize_host(host_path, staging.read_bytes(), package_path,
                expected_revision=self.store.snapshot()['revision'], fault=fault)

    def bind(self, entity_id, host_object, subelement):
        assert_thread()
        if entity_id not in self.objects or host_object.Document != self.doc or not subelement.startswith('Face'):
            reject('attachment_reassignment_required')
        if hasattr(host_object,'FCSTKind') and host_object.FCSTKind not in ('geometry','face'):
            reject('attachment_reassignment_required')
        if not hasattr(host_object,'FCSTEntityId'):
            face_id=self.capture_surface(host_object,subelement)
            face=next(e for e in self.store.snapshot()['entities'] if e['id']==face_id)
            return self.bind(entity_id,self.objects[face['geometry_id']],subelement)
        face = host_object.Shape.getElement(subelement)
        signature = shape_signature(face)
        self.store.mark_host_dirty()
        with self.projection():
            obj = self.objects[entity_id]
            obj.FCSTAttachment = (host_object, [subelement])
            obj.FCSTAttachmentSignature = signature
            obj.FCSTSourceRevision = shape_signature(host_object.Shape)
            obj.FCSTAttachmentState = 'assigned'
        self.clear_display()
        self.draw_bindings()

    def capture_surface(self, host_object, subelement):
        """Freeze owned CAD bytes, then create the geometry and signed face atomically."""
        assert_thread()
        if host_object.Document != self.doc or not subelement.startswith('Face'):
            reject('attachment_reassignment_required')
        face = host_object.Shape.getElement(subelement)
        raw = host_object.Shape.exportBrepToString().encode()
        geometry_id, face_id, artifact_id, frame_id = (str(uuid.uuid4()) for _ in range(4))
        path = 'geometry/'+geometry_id+'.brep'
        model = self.store.snapshot()
        self.store.add_artifact(artifact_id,'geometry',path,raw,expected_revision=model['revision'])
        frame=dict(id=frame_id,kind='frame',origin=[dict(value=0,unit='m') for _ in range(3)],rotation=[[1,0,0],[0,1,0],[0,0,1]])
        geometry = dict(id=geometry_id,kind='geometry',frame_id=frame_id,artifact=dict(path=path,sha256=sha256(raw).hexdigest(),byte_length=len(raw)),revision=0)
        face_value = dict(id=face_id,kind='face',geometry_id=geometry_id,persistent_ref=subelement,
            signature=shape_signature(face),area=dict(value=face.Area*1e-6,unit='m2'))
        self.store.apply('local-workbench',{'changes.apply'},model['project_id'],model['revision'],str(uuid.uuid4()),
                         dict(upsert=[frame,geometry,face_value],delete=[]))
        self.store.mark_host_dirty(); self.clear_display(); self.project()
        self.diverged = False
        with self.projection():host_object.ViewObject.Visibility=False
        return face_id

    def check_bindings(self):
        assert_thread()
        bad = []
        with self.projection():
            for key, obj in self.objects.items():
                if not obj.FCSTAttachment:
                    continue
                host, names = obj.FCSTAttachment
                try:
                    if (len(names) != 1 or shape_signature(host.Shape.getElement(names[0])) != obj.FCSTAttachmentSignature
                            or shape_signature(host.Shape) != obj.FCSTSourceRevision
                            or sum(shape_signature(face)==obj.FCSTAttachmentSignature for face in host.Shape.Faces)!=1):
                        raise ValueError()
                    obj.FCSTAttachmentState = 'assigned'
                except (ValueError, RuntimeError, AttributeError, ReferenceError):
                    obj.FCSTAttachmentState = 'invalid / reassign'
                    bad.append(key)
        if bad:
            self.store.mark_host_dirty()
            self.clear_display()
        return bad

    def clear_display(self):
        self.result = None
        if self.spatial_view is not None:
            self.spatial_view.hide()
        if hasattr(self, 'objects'):
            for key in self.objects:
                obj=self.doc.getObject('FCST_'+key.replace('-',''))
                if obj is None:continue
                if obj.FCSTKind == 'node':
                    obj.ViewObject.ShapeColor = (.48,.48,.48)
                elif obj.FCSTKind=='geometry':obj.ViewObject.DiffuseColor=[(.65,.65,.65)]*len(obj.Shape.Faces)

    def import_field(self,value):
        from fcst_contracts import read
        from .spatial import SpatialView
        value=read('spatial',value)
        view=SpatialView(self,value)
        artifact_id=str(uuid.uuid4())
        self.store.add_artifact(artifact_id,'evidence','review-fields/'+artifact_id+'.json',encode(value),
                                expected_revision=self.store.snapshot()['revision'])
        self.spatial_view=view
        self.spatial_id=artifact_id
        return view

    def load_result(self, result_id):
        assert_thread()
        if self.check_bindings():
            reject('attachment_reassignment_required')
        if self.diverged:
            reject('host_reconciliation_required')
        self.result = review.query_result(self.store, result_id)
        self.result_id = result_id
        return self.result

    def show_sample(self, index, selected=None, unit='K'):
        assert_thread()
        if self.result_id is None:
            reject('result_unavailable')
        # Re-query freshness every time; cached fields never grant current status.
        result = review.query_result(self.store, self.result_id)
        if self.diverged:
            reject('host_reconciliation_required')
        if self.check_bindings():
            reject('attachment_reassignment_required')
        value = review.display(result, index, selected, unit)
        with self.projection():
            for key, rgb in zip(result['node_ids'], value['colours']):
                self.objects[key].ViewObject.ShapeColor = rgb
                obj=self.objects[key]
                if obj.FCSTAttachment:
                    target,names=obj.FCSTAttachment
                    colours=list(target.ViewObject.DiffuseColor)
                    if len(colours)!=len(target.Shape.Faces):colours=[target.ViewObject.ShapeColor]*len(target.Shape.Faces)
                    colours[int(names[0][4:])-1]=rgb
                    target.ViewObject.DiffuseColor=colours
        return value

    def close(self):
        import FreeCAD as App
        if self.closed:
            return
        if self.job is not None:
            self.job.cancel()
            self.job.process.waitForFinished(1000)
        if self.spatial_view is not None:
            self.spatial_view.remove_overlay()
        if self.panel is not None:
            self.panel.close();self.panel.deleteLater()
        self.closed = True
        App.removeDocumentObserver(self.observer)
        self.store.close()
