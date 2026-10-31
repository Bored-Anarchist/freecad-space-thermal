# SPDX-License-Identifier: LGPL-2.1-or-later
"""Existing FEM field display and explicit engineering overlays, on the GUI thread."""
import math
from fcst_contracts import read
from fcst_contracts.spatial import field_global, integrated_boundary_power
from fcst_app import fem_adapter
from fcst_app.persistence import reject, semantic_hash
from .review import colour


class SpatialView:
    def __init__(self, session, value):
        self.session=session
        self.value=read('spatial',value)
        if self.value['model_hash']!=semantic_hash(session.store.snapshot()): reject('stale_result')
        if self.value['project_id']!=session.store.snapshot()['project_id']: reject('result_identity')
        with session.projection():
            self.mesh,self.result=fem_adapter.create(session.doc,self.value)
            self.mesh.ViewObject.Visibility=False
        self.overlay=None
        import FreeCADGui as Gui
        self.scene=Gui.getDocument(session.doc.Name).activeView().getSceneGraph()
        self.sample=0
        self.displayed_scalars=[]

    def show(self, quantity='temperature', sample=0):
        import FreeCAD as App
        from pivy import coin
        import FreeCADGui as Gui
        fem_adapter.assert_thread()
        value=self.value
        if (self.session.diverged or value['model_hash']!=semantic_hash(self.session.store.snapshot())
                or self.session.check_bindings()):
            self.hide(); reject('stale_result')
        if not 0 <= sample < len(value['times']): reject('result_selection')
        root=coin.SoSeparator()
        def line(a,b,rgb):
            group=coin.SoSeparator(); material=coin.SoBaseColor(); material.rgb=rgb
            coords=coin.SoCoordinate3(); coords.point.setValues(0,2,[a,b])
            lines=coin.SoLineSet(); lines.numVertices=2
            group.addChild(material); group.addChild(coords); group.addChild(lines); root.addChild(group)
        points=[[x*1000 for x in v] for v in value['vertices']]
        with self.session.projection():
            self.mesh.ViewObject.DisplayMode='Faces'
            self.mesh.ViewObject.Visibility=True
            self.session.doc.recompute()
            if quantity in ('temperature','heat_flux'):
                vectors=field_global(value,quantity,sample)
                scalars=[v[0] if len(v)==1 else math.sqrt(sum(x*x for x in v)) for v in vectors]
                self.displayed_scalars=scalars
                # NodeColor's getter is unavailable on the pinned host. Its
                # setter is implemented and preserves a fixed scale across time.
                all_vectors=[field_global(value,quantity,i) for i in range(len(value['times']))]
                all_scalars=[v[0] if len(v)==1 else math.sqrt(sum(x*x for x in v)) for row in all_vectors for v in row]
                lo,hi=min(all_scalars),max(all_scalars)
                self.displayed_colours={int(i):colour(v,lo,hi) for i,v in zip(self.result.NodeNumbers,scalars)}
                self.mesh.ViewObject.ColorMode='ByNode'
                self.mesh.ViewObject.NodeColor=self.displayed_colours
                if quantity=='temperature': self.result.Temperature=scalars
                else:
                    self.result.HeatFlux=[App.Vector(*v) for v in vectors]
                    scale=100/(max(scalars) or 1)
                    for p,v in zip(points,vectors): line(p,[p[k]+v[k]*scale for k in range(3)],(.2,.8,.7))
            elif quantity=='normals':
                for cell in value['cells']:
                    if cell['topology']!='tri3': continue
                    a,b,c=[App.Vector(*points[int(i)]) for i in cell['vertices']]
                    n=(b-a).cross(c-a); n.normalize(); center=(a+b+c)/3
                    line(tuple(center),tuple(center+n*100),(.98,.8,.22))
            elif quantity=='material_axes':
                frame=next(f['basis'] for f in value['frames'] if f['id']==value['material']['frame_id'])
                for i,rgb in enumerate(((1,.3,.3),(.3,1,.3),(.3,.5,1))):
                    line([0,0,0],[frame[k][i]*200 for k in range(3)],rgb)
            else: reject('result_selection')
        self.remove_overlay()
        self.scene.addChild(root); self.overlay=root
        return dict(unit='K' if quantity=='temperature' else 'W/m2' if quantity=='heat_flux' else '1',
            time_s=value['times'][sample],vertex_ids=value['vertex_ids'],
            integrated_flux_W={c['id']:integrated_boundary_power(value,c['id'],sample) for c in value['cells'] if c['topology']=='tri3'} if any(f['quantity']=='heat_flux' for f in value['fields']) else {})

    def remove_overlay(self):
        if self.overlay is not None:
            if self.scene.findChild(self.overlay)>=0:self.scene.removeChild(self.overlay)
            self.overlay=None

    def hide(self):
        self.remove_overlay()
        try:self.mesh.ViewObject.Visibility=False
        except (ReferenceError,RuntimeError):pass
