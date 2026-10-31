# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run by a generated local macro, inside the pinned GUI with an active Qt loop."""
import json
import os
from pathlib import Path
import sys
import traceback

from PySide6 import QtCore, QtGui, QtWidgets, QtTest
import FreeCAD as App
import FreeCADGui as Gui
import Part

folder=Path(os.environ['FCST_HOST_OUTPUT'])
sys.path.insert(0,os.environ['FCST_HOST_ADDON'])


def main():
    from copy import deepcopy
    import threading
    import time
    import math
    from fcst_contracts import loads, read, normalize
    from fcst_app.persistence import Package, PersistenceError, semantic_hash
    from fcst_app.store import ProjectStore
    from fcst_app import fem_adapter
    from fcst_host import review, workbench
    from fcst_host.controller import Session
    from fcst_host.widgets import EntityEditor, NativeJob, SettingsEditor
    from fcst_host.spatial import SpatialView
    cases=[]
    def mark(phase):
        (folder/'stage.json').write_text(json.dumps(dict(phase=phase)))
    def passed(case):
        cases.append(dict(id=case,status='passed'))
        (folder/'progress.json').write_text(json.dumps(cases))
    def wait(predicate,seconds=30):
        deadline=time.monotonic()+seconds
        while not predicate():
            QtWidgets.QApplication.processEvents(); QtTest.QTest.qWait(10)
            assert time.monotonic()<deadline,'host_deadline'
    def rejects(call,code):
        try: call()
        except PersistenceError as e: assert e.code==code
        else: raise AssertionError('missing_rejection')
    assert list(App.Version()[:3])==['1','1','4'] and sys.version_info[:2]==(3,11)
    workbench.register(); Gui.activateWorkbench('FCSTWorkbench')
    session=Session.create(folder/'model',review.example_model())
    panel=workbench.show(session); panel.worker=os.environ['FCST_HOST_WORKER']
    Gui.getMainWindow().resize(1280,900); Gui.getMainWindow().show()
    assert session.root.TypeId=='Fem::FemAnalysis'
    assert len(session.objects)==4
    passed('FEM-REUSE-001')
    original=session.store.snapshot(); node=deepcopy(original['entities'][1]); node['temperature']=dict(value=36.85,unit='degC')
    with ProjectStore.create(folder/'standalone.db',original) as standalone:
        actual=session.edit(node)
        expected=review.change(standalone,node,expected_revision=0)
        assert actual==expected
    session.undo(); assert semantic_hash(session.store.snapshot())==semantic_hash(original)
    for temperature in (315,320):
        entity=deepcopy(session.store.snapshot()['entities'][1]);entity['temperature']=dict(value=temperature,unit='K')
        session.edit(entity)
    session.save(folder/'undo-history.FCStd',folder/'undo-history.fcst')
    undo_session=Session.open(folder/'undo-history.fcst',folder/'undo-history-reopened')
    for temperature in (315,310):
        undo_session.undo()
        assert next(e for e in undo_session.store.snapshot()['entities'] if e['id']==review.uid(4))['temperature']['value']==temperature
    rejects(undo_session.undo,'unknown_revision')
    undo_session.close();App.closeDocument(undo_session.doc.Name);App.setActiveDocument(session.doc.Name)
    session.undo();session.undo()
    assert semantic_hash(session.store.snapshot())==semantic_hash(original)
    passed('HOST-UNDO-HISTORY')
    session.save(folder/'saved.FCStd',folder/'saved.fcst')
    assert session.store.state()['host']['dirty'] is False
    assert Package.open(folder/'saved.fcst').model==session.store.snapshot()
    passed('FEM-REUSE-002')
    # Every required editor kind is instantiated from its exact frozen schema.
    templates=json.loads((Path(os.environ['FCST_HOST_ADDON'])/'fcst_host/templates.json').read_bytes())
    for kind in ('node','face','facet','material','optics','conductor','load','environment','case'):
        editor=EntityEditor(session,templates[kind],panel)
        assert editor.value()==templates[kind]
        editor.close()
    editor=EntityEditor(session,original['entities'][1],panel); editor.show()
    before_invalid=session.store.snapshot()['revision']
    editor.fields['temperature'][1].setText('-1'); editor.fields['temperature'][2].setCurrentText('K')
    editor.commit(); assert editor.error.text() and session.store.snapshot()['revision']==before_invalid
    editor.fields['temperature'][1].setText('36.85'); editor.fields['temperature'][2].setCurrentText('degC')
    editor.commit(); assert editor.result()==QtWidgets.QDialog.Accepted
    node=next(e for e in session.store.snapshot()['entities'] if e['id']==review.uid(4))
    assert abs(normalize(node)['temperature']['value']-310)<1e-12
    options=SettingsEditor(session,panel); options.fields['samples'].setText('21'); options.commit()
    assert options.result()==QtWidgets.QDialog.Accepted
    passed('HOST-EDITORS')
    load=dict(id=review.uid(9),kind='load',node_id=review.uid(4),power=dict(value=2000,unit='mW'))
    session.edit(load)
    assert next(e for e in session.store.snapshot()['entities'] if e['id']==review.uid(9))['power']==dict(value=2,unit='W')
    session.undo()
    passed('FEM-REUSE-004')
    panel.refresh(); panel.select_entity(review.uid(5))
    assert panel.selected==review.uid(5) and Gui.Selection.getSelection()[0].FCSTEntityId==review.uid(5)
    Gui.Selection.clearSelection(); Gui.Selection.addSelection(session.objects[review.uid(4)])
    assert panel.selected==review.uid(4)
    passed('HOST-SELECTION')
    QtTest.QTest.mouseClick(panel.run,QtCore.Qt.LeftButton)
    wait(lambda:session.job is not None and session.job.state not in ('queued','running'))
    assert session.job.state=='succeeded',session.job.state
    result=session.result; assert len(result['samples'])==21
    assert abs(result['samples'][-1]['temperature_K'][0]-(298+12*math.exp(-20/3)))<.01
    assert abs(result['samples'][-1]['run_energy']['defect_J'])<1e-7
    assert panel.progress.value()==1 and 'CURRENT' in panel.status.text()
    panel.time.setValue(10); panel.unit.setCurrentText('degC')
    assert panel.history.points==review.display(result,10,review.uid(4),'degC')['history']
    passed('HOST-SOLVE')
    session.save(folder/'solved.FCStd',folder/'solved.fcst')
    reopened=Session.open(folder/'solved.fcst',folder/'reopened')
    assert reopened.result is not None and reopened.result['samples']==result['samples']
    reopened.close(); App.closeDocument(reopened.doc.Name)
    App.setActiveDocument(session.doc.Name)
    job=NativeJob(session,panel.worker); session.job=job; job.start(); job.cancel()
    wait(lambda:job.process.state()==QtCore.QProcess.NotRunning)
    assert job.state=='cancelled'
    passed('HOST-CANCEL')
    race=NativeJob(session,panel.worker);session.job=race;race.start()
    changed=deepcopy(session.store.snapshot()['entities'][1]);changed['capacity']=dict(value=4,unit='J/K')
    session.edit(changed)
    wait(lambda:race.state not in ('queued','running'))
    assert race.state=='rejected' and session.result is None
    session.undo()
    passed('HOST-ASYNC-RACE')
    def interrupted(point):
        if point=='host_replace': raise RuntimeError('synthetic_interruption')
    try: session.save(folder/'interrupted.FCStd',folder/'interrupted.fcst',fault=interrupted)
    except RuntimeError: pass
    else: raise AssertionError('missing_save_fault')
    assert session.store.state()['host']['dirty']
    session.save(folder/'recovered.FCStd',folder/'recovered.fcst')
    assert not session.store.state()['host']['dirty']
    passed('HOST-SAVE-RECOVERY')
    box=session.doc.addObject('PartDesign::Feature','OwnedBox'); box.Shape=Part.makeBox(10,20,30)
    session.bind(review.uid(4),box,'Face1'); assert not session.check_bindings()
    bound=session.objects[review.uid(4)].FCSTAttachment[0]
    bound.Shape=Part.makeBox(11,20,30)
    assert review.uid(4) in session.check_bindings()
    assert session.objects[review.uid(4)].FCSTAttachmentState=='invalid / reassign'
    rejects(lambda:session.load_result(session.result_id),'attachment_reassignment_required')
    original_bound=bound.Shape.copy()
    for changed_shape in (Part.makeBox(12,20,30),original_bound.cut(Part.makeBox(5,20,30)),
                          original_bound.fuse(Part.makeBox(10,20,30,App.Vector(10,0,0))),
                          Part.makeCompound(list(reversed(original_bound.Faces))),Part.Shape()):
        bound.Shape=changed_shape
        assert review.uid(4) in session.check_bindings()
    session.doc.removeObject(box.Name)
    passed('HOST-TOPOLOGY')
    failures=[]
    def wrong_thread():
        try: session.project()
        except PersistenceError as e: failures.append(e.code)
    thread=threading.Thread(target=wrong_thread); thread.start(); thread.join()
    assert failures==['host_thread']
    passed('HOST-THREAD')
    # Build a reference model through workbench commands and editor controls only.
    Gui.runCommand('FCST_New')
    built=workbench.current(); built.panel.worker=panel.worker
    def add(kind,changes=None):
        Gui.runCommand('FCST_Add_'+kind)
        dialogs=[w for w in built.panel.findChildren(EntityEditor) if w.isVisible()]
        assert len(dialogs)==1
        dialog=dialogs[0]
        if changes: changes(dialog)
        identifier=dialog.entity['id']; dialog.commit()
        assert dialog.result()==QtWidgets.QDialog.Accepted,dialog.error.text()
        QtWidgets.QApplication.processEvents()
        return identifier
    submodel_id=add('submodel')
    def reservoir(d):
        d.fields['classification'][1].setCurrentText('prescribed')
        d.fields['capacity'][1].setText('0')
    reservoir_id=add('node',reservoir)
    free_id=add('node')
    add('conductor')
    def heating(d):
        d.fields['node_id'][1].setCurrentText(free_id)
        d.fields['power'][1].setText('2');d.fields['power'][2].setCurrentText('W')
    add('load',heating)
    controls=SettingsEditor(built,built.panel);controls.fields['mode'].setCurrentText('steady');controls.commit()
    assert controls.result()==QtWidgets.QDialog.Accepted
    QtTest.QTest.mouseClick(built.panel.run,QtCore.Qt.LeftButton)
    wait(lambda:built.job is not None and built.job.state not in ('queued','running'))
    assert built.job.state=='succeeded',built.job.state
    values=dict(zip(built.result['node_ids'],built.result['samples'][0]['temperature_K']))
    assert values[reservoir_id]==300 and abs(values[free_id]-301)<1e-7
    # Capture actual selected CAD; reopening reconstructs its signed face from BREP.
    owned=built.doc.addObject('PartDesign::Feature','SyntheticPanel');owned.Shape=Part.makeBox(1000,1000,20)
    Gui.Selection.clearSelection();Gui.Selection.addSelection(owned,'Face1')
    Gui.runCommand('FCST_Surface')
    faces=[e for e in built.store.snapshot()['entities'] if e['kind']=='face'];assert len(faces)==1,built.panel.status.text()
    assert built.objects[faces[0]['id']].FCSTAttachmentState=='assigned'
    geometry=next(e for e in built.store.snapshot()['entities'] if e['id']==faces[0]['geometry_id'])
    frame=next(e for e in built.store.snapshot()['entities'] if e['id']==geometry['frame_id'])
    frame_editor=EntityEditor(built,frame,built.panel)
    frame_editor.fields['origin'][1].setPlainText(json.dumps([dict(value=2,unit='m'),dict(value=0,unit='mm'),dict(value=0,unit='m')]))
    frame_editor.fields['rotation'][1].setPlainText(json.dumps([[0,-1,0],[1,0,0],[0,0,1]]))
    frame_editor.commit();assert frame_editor.result()==QtWidgets.QDialog.Accepted
    body=built.objects[geometry['id']]
    assert abs(body.Shape.BoundBox.XMin-1000)<1e-7
    assert abs(built.objects[faces[0]['id']].Shape.CenterOfMass.x-1500)<1e-7
    built.bind(free_id,body,'Face1');built.panel.refresh()
    Gui.Selection.clearSelection();Gui.Selection.addSelection(body,'Face1')
    assert built.panel.selected==free_id
    assert built.doc.getObject('FCSTMapping_'+free_id.replace('-','')).Shape.Length>1000
    QtTest.QTest.mouseClick(built.panel.run,QtCore.Qt.LeftButton)
    wait(lambda:built.job.state not in ('queued','running'))
    assert built.job.state=='succeeded'
    assert 'energy defect W' in built.panel.budget.toPlainText()
    colors=review.display(built.result,0)['colours'];expected=colors[built.result['node_ids'].index(free_id)]
    assert max(abs(a-b) for a,b in zip(body.ViewObject.DiffuseColor[0],expected))<1e-6
    passed('HOST-FRAME')
    built.save(folder/'built.FCStd',folder/'built.fcst')
    copied=Session.open(folder/'built.fcst',folder/'built-reopened')
    assert copied.options['mode']=='steady' and copied.store.snapshot()==built.store.snapshot()
    assert copied.objects[faces[0]['id']].FCSTAttachmentState=='assigned'
    assert abs(copied.objects[geometry['id']].Shape.BoundBox.XMin-1000)<1e-7
    copied.close();App.closeDocument(copied.doc.Name)
    built.close();App.closeDocument(built.doc.Name);App.setActiveDocument(session.doc.Name)
    passed('HOST-CREATE')
    with ProjectStore.create(folder/'invalid-review.db',review.example_model()) as broken:
        broken.add_artifact(review.uid(100),'evidence','review-settings/invalid.json',
            b'{"sequence":"invalid","options":{},"case_id":null,"bindings":[]}',expected_revision=0)
        broken.save(folder/'invalid-review.fcst')
    before_documents=set(App.listDocuments())
    rejects(lambda:Session.open(folder/'invalid-review.fcst',folder/'invalid-reopen'),'review_configuration')
    assert set(App.listDocuments())==before_documents
    passed('HOST-PACKAGE-RECOVERY')
    # Pinned FEM field path verifies raw vector values and actual contour scalars.
    model=loads((Path(os.environ['FCST_HOST_ROOT'])/'tests/fixtures/contracts/network.json').read_bytes())
    value=loads((Path(os.environ['FCST_HOST_ROOT'])/'tests/fixtures/spatial/solid-surface-rotated.json').read_bytes())
    doc=App.newDocument('FCSTFields')
    mark('fem_create')
    mesh,field=fem_adapter.create(doc,value)
    assert fem_adapter.query(field,value,semantic_hash(model))['heat_flux']==[[-3,2,8]]*4
    # Both setters work; inspect the exact getter limitation without relying on it.
    mark('fem_colour_setter')
    mesh.ViewObject.setNodeColorByScalars(field.NodeNumbers,field.Temperature)
    try: unused=mesh.ViewObject.NodeColor
    except AttributeError as error: assert str(error)=='Not yet implemented'
    else: raise AssertionError('pinned_contour_disposition_changed')
    mark('fem_save_reopen')
    doc.saveAs(str(folder/'fields.FCStd')); App.closeDocument(doc.Name)
    doc=App.openDocument(str(folder/'fields.FCStd'))
    assert fem_adapter.query(doc.FCSTResult,value,semantic_hash(model))['temperature']==[[300],[301],[302],[303]]
    rejects(lambda:fem_adapter.query(doc.FCSTResult,value,'0'*64),'stale_result')
    App.closeDocument(doc.Name)
    field_session=Session.create(folder/'field-session',model)
    mark('field_native_solve')
    field_job=NativeJob(field_session,panel.worker);field_session.job=field_job;field_job.start()
    wait(lambda:field_job.state not in ('queued','running'))
    assert field_job.state=='succeeded' and field_session.result is not None
    network_result_id=field_session.result_id
    mark('spatial_import')
    field_view=field_session.import_field(value)
    assert field_session.result is None and field_session.result_id is None
    field_panel=workbench.show(field_session);field_panel.unit.setCurrentText('degC')
    field_panel.time.setValue(1);field_panel.field_vertex.setCurrentIndex(2)
    assert field_panel.history.points==[(0,302-273.15),(1,302-273.15)]
    assert 'CURRENT' in field_panel.status.text() and 'degC' in field_panel.legend.text()
    mark('spatial_temperature')
    field_view.show('temperature',1);assert field_view.displayed_scalars==[300,301,302,303]
    actual_colours=[list(c) for c in field_view.mesh.ViewObject.NodeColorArray]
    assert len(actual_colours)==4
    for i,rgb in enumerate(actual_colours,1):
        assert max(abs(a-b) for a,b in zip(rgb,field_view.displayed_colours[i]))<1e-6
    mark('spatial_vectors')
    field_view.show('heat_flux',1);assert field_view.result.HeatFlux[0]==App.Vector(-3,2,8)
    mark('spatial_normals');field_view.show('normals')
    mark('spatial_axes');field_view.show('material_axes')
    field_view.show('temperature');Gui.Selection.clearSelection();Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll();Gui.updateGui()
    mark('spatial_capture')
    Gui.activeDocument().activeView().saveImage(str(folder/'contour.png'),900,650,'Current')
    contour=QtGui.QImage(str(folder/'contour.png'));blue=teal=0
    for x in range(contour.width()):
        for y in range(contour.height()):
            c=contour.pixelColor(x,y)
            if c.blue()>c.red()*1.2 and c.blue()>70:blue+=1
            if c.green()>c.red()*1.2 and c.green()>70:teal+=1
    assert blue>100 and teal>100,'native_contour_not_coloured'
    field_session.save(folder/'spatial.FCStd',folder/'spatial.fcst')
    mark('multi_document')
    other=App.newDocument('OtherReviewDocument');marker=other.addObject('PartDesign::Feature','UnrelatedMarker');marker.Shape=Part.makeBox(1,2,3)
    other_scene=Gui.getDocument(other.Name).activeView().getSceneGraph()
    field_view.show('normals')
    assert other_scene.findChild(field_view.overlay)==-1 and field_view.scene.findChild(field_view.overlay)>=0
    owner_name=field_session.doc.Name;App.closeDocument(owner_name)
    assert field_session.closed and abs(marker.Shape.Volume-6)<1e-12
    App.closeDocument(other.Name)
    passed('HOST-MULTI-DOCUMENT')
    mark('dataset_restore')
    spatial_reopened=Session.open(folder/'spatial.fcst',folder/'spatial-reopened')
    assert spatial_reopened.spatial_view is not None and spatial_reopened.spatial_view.value==value and spatial_reopened.result is None
    spatial_reopened.load_result(network_result_id)
    assert spatial_reopened.spatial_view is None and spatial_reopened.result is not None
    spatial_reopened.save(folder/'network-selected.FCStd',folder/'network-selected.fcst')
    spatial_reopened.close();App.closeDocument(spatial_reopened.doc.Name)
    network_reopened=Session.open(folder/'network-selected.fcst',folder/'network-selected')
    assert network_reopened.spatial_view is None and network_reopened.result is not None
    network_reopened.close();App.closeDocument(network_reopened.doc.Name)
    passed('FEM-REUSE-005')
    session.close();App.closeDocument(session.doc.Name)
    mark('final_render')
    session=Session.open(folder/'solved.fcst',folder/'render-reopened')
    panel=workbench.show(session);panel.select_entity(review.uid(4));panel.time.setValue(10)
    QtWidgets.QApplication.processEvents(); QtTest.QTest.qWait(100)
    image=panel.history.grab().toImage()
    assert image.width()>=300 and image.height()>=100
    coloured=0
    for x in range(image.width()):
        for y in range(image.height()):
            c=image.pixelColor(x,y)
            if c.green()>130 and c.blue()>100 and c.red()<120: coloured+=1
    assert coloured>=40
    panel.grab().save(str(folder/'review.png'))
    Gui.activeDocument().activeView().saveImage(str(folder/'network.png'),900,650,'Current')
    passed('HOST-RENDER')
    session.close(); App.closeDocument(session.doc.Name)
    (folder/'host.json').write_text(json.dumps(dict(host_version=['1','1','4'],python_abi='cp311',
        cases=cases,spatial_solver_qualified=False,scope='WP-13 host workflows and supported FEM field display; production spatial physics remains WP-16'),indent=2)+'\n')


def run():
    (folder/'started.json').write_text('{"phase":"tests_started"}\n')
    try:
        main()
    except BaseException:
        (folder/'payload-error.log').write_text(traceback.format_exc())
        os._exit(1)
    os._exit(0)


QtCore.QTimer.singleShot(500,run)
