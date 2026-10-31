# SPDX-License-Identifier: LGPL-2.1-or-later
"""Native Qt editors and linked result review. No external plotting dependency."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import uuid

from PySide6 import QtCore, QtGui, QtWidgets
from fcst_contracts import BUNDLE, ContractError, loads
from fcst_app.persistence import PersistenceError, encode, reject
from . import review


def diagnostic(error):
    if isinstance(error, ContractError):
        d = error.diagnostic
        return 'Validation: '+d.code+' '+d.pointer
    if isinstance(error, PersistenceError):
        return 'Project: '+error.code
    return 'Operation failed; project remains available for recovery.'


class EntityEditor(QtWidgets.QDialog):
    """Schema-derived scalar/quantity/reference form plus inert structured fields."""
    def __init__(self, session, entity, parent=None):
        super().__init__(parent)
        self.setObjectName('FCSTEntityEditor')
        self.setWindowTitle('Edit '+entity['kind'].title())
        self.resize(590, 620)
        self.session, self.entity = session, deepcopy(entity)
        self.revision = session.store.snapshot()['revision']
        self.fields = {}
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel('THERMAL MODEL  /  '+entity['kind'].upper())
        layout.addWidget(title)
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True)
        body = QtWidgets.QWidget(); form = QtWidgets.QFormLayout(body)
        schema = BUNDLE['schemas']['model']['$defs'][entity['kind']]
        for key, value in {**entity,'label':entity.get('label','')}.items():
            if key in ('id', 'kind'):
                label = QtWidgets.QLabel(str(value)); label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
                form.addRow(key.title(), label)
                continue
            field_schema = schema['properties'].get(key, {})
            if isinstance(value, dict) and set(value) == {'value', 'unit'}:
                widget = QtWidgets.QWidget(); row = QtWidgets.QHBoxLayout(widget); row.setContentsMargins(0,0,0,0)
                scalar = QtWidgets.QLineEdit(format(value['value'], '.15g'))
                scalar.setObjectName('FCSTField_'+key+'_value')
                unit = QtWidgets.QComboBox(); unit.setEditable(True)
                unit.addItems(sorted(BUNDLE['units'])); unit.setCurrentText(value['unit'])
                unit.setObjectName('FCSTField_'+key+'_unit')
                row.addWidget(scalar, 2); row.addWidget(unit, 1)
                self.fields[key] = ('quantity', scalar, unit)
            elif key.endswith('_id'):
                widget = QtWidgets.QComboBox(); widget.setEditable(True)
                for e in session.store.snapshot()['entities']:
                    widget.addItem(e['id'])
                widget.setCurrentText(str(value))
                self.fields[key] = ('reference', widget)
            elif 'enum' in field_schema:
                widget = QtWidgets.QComboBox(); widget.addItems(field_schema['enum']); widget.setCurrentText(value)
                self.fields[key] = ('reference', widget)
            elif isinstance(value, (dict, list)):
                widget = QtWidgets.QPlainTextEdit(json.dumps(value, indent=2)); widget.setMaximumHeight(150)
                self.fields[key] = ('json', widget)
            else:
                widget = QtWidgets.QLineEdit(str(value))
                self.fields[key] = ('number' if type(value) in (int,float) else 'text', widget)
            widget.setObjectName('FCSTField_'+key)
            form.addRow(key.replace('_',' ').title(), widget)
        scroll.setWidget(body); layout.addWidget(scroll)
        self.error = QtWidgets.QLabel(); self.error.setObjectName('FCSTEditorError'); self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.setObjectName('FCSTEditorButtons'); buttons.accepted.connect(self.commit); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self):
        entity = deepcopy(self.entity)
        for key, field in self.fields.items():
            kind, widget, *rest = field
            if kind == 'quantity':
                entity[key] = dict(value=float(widget.text()), unit=rest[0].currentText())
            elif kind == 'reference':
                entity[key] = widget.currentText()
            elif kind == 'json':
                entity[key] = loads(widget.toPlainText())
            elif kind == 'number':
                entity[key] = float(widget.text())
            else:
                if key=='label' and not widget.text():entity.pop(key,None)
                else:entity[key] = widget.text()
        return entity

    def commit(self):
        try:
            self.session.edit(self.value(), expected_revision=self.revision)
            self.accept()
            if self.session.on_change:
                self.session.on_change()
        except (ValueError, OSError) as e:
            self.error.setText(diagnostic(e))


class SettingsEditor(QtWidgets.QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Solver settings'); self.setObjectName('FCSTSolverSettings')
        self.session = session; self.fields = {}
        form = QtWidgets.QFormLayout(self)
        for key, value in session.options.items():
            if key=='mode':
                edit=QtWidgets.QComboBox();edit.addItems(['steady','transient']);edit.setCurrentText(value)
            else:edit = QtWidgets.QLineEdit(str(value))
            edit.setObjectName('FCSTSetting_'+key)
            self.fields[key] = edit
            form.addRow(key.replace('_',' ').title(), edit)
        self.error = QtWidgets.QLabel(); form.addRow(self.error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.commit); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def commit(self):
        try:
            self.session.options = review.settings({k: w.currentText() if k=='mode' else float(w.text()) for k,w in self.fields.items()})
            self.accept()
        except ValueError as e:
            self.error.setText(diagnostic(e))


class History(QtWidgets.QWidget):
    def __init__(self):
        super().__init__(); self.setObjectName('FCSTHistory'); self.setMinimumHeight(165)
        self.points, self.unit = [], 'K'

    def paintEvent(self, event):
        p = QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor('#122535'))
        p.setPen(QtGui.QColor('#9fb4c5')); p.drawText(14,22,'NODE HISTORY  /  '+self.unit)
        if not self.points:
            p.drawText(16,65,'Select a current result and thermal node.'); return
        xs, ys = zip(*self.points); lo, hi = min(ys), max(ys)
        p.drawText(12,48,format(hi,'.5g')); p.drawText(12,self.height()-26,format(lo,'.5g'))
        p.drawText(self.width()-95,self.height()-8,format(max(xs),'.4g')+' s')
        path = QtGui.QPainterPath()
        for i, (x,y) in enumerate(self.points):
            point = QtCore.QPointF(65+(self.width()-85)*(x-min(xs))/(max(xs)-min(xs) or 1),
                self.height()-32-(self.height()-90)*(y-lo)/(hi-lo or 1))
            if i: path.lineTo(point)
            else: path.moveTo(point)
        p.setPen(QtGui.QPen(QtGui.QColor('#42c6bb'),2.5)); p.drawPath(path)


class NativeJob(QtCore.QObject):
    """Qt event-loop process supervision. All store/host mutations stay on this thread."""
    changed = QtCore.Signal(str)
    def __init__(self, session, worker, *, timeout_ms=120000):
        super().__init__()
        self.session, self.worker = session, Path(worker).resolve()
        if session.diverged or session.check_bindings(): reject('host_reconciliation_required')
        if not self.worker.is_file(): reject('worker_unavailable')
        self.model = session.store.snapshot()
        self.flag, self.input = review.request(self.model, session.options, session.case_id)
        self.worker_hash = sha256(self.worker.read_bytes()).hexdigest()
        self.id = str(uuid.uuid4()); self.state = 'queued'; self.output = bytearray(); self.error_bytes = 0
        session.store.db.execute('CREATE TABLE IF NOT EXISTS host_runs (id TEXT PRIMARY KEY, state TEXT NOT NULL, revision INTEGER NOT NULL, worker_sha256 TEXT NOT NULL)')
        # An abandoned operational run can never publish after restart.
        session.store.db.execute("UPDATE host_runs SET state='interrupted' WHERE state IN ('queued','running')")
        session.store.db.execute('INSERT INTO host_runs VALUES(?,?,?,?)', (self.id,self.state,self.model['revision'],self.worker_hash))
        self.process = QtCore.QProcess(self)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        for key in ('PYTHONPATH','PYTHONHOME','FREECAD_LIB','SINDAPATH','ESATAN'):
            env.remove(key)
        env.insert('PATH',str(self.worker.parent)); env.insert('OMP_NUM_THREADS','1')
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(session.workspace))
        self.process.started.connect(self.started)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)
        self.timer = QtCore.QTimer(self); self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.stop('timeout'))
        self.timeout_ms = timeout_ms

    def update(self, state):
        self.state = state
        if not self.session.closed:
            self.session.store.db.execute('UPDATE host_runs SET state=? WHERE id=?',(state,self.id))
        self.changed.emit(state)

    def start(self):
        self.timer.start(self.timeout_ms)
        self.process.start(str(self.worker), [self.flag])

    def started(self):
        if self.state != 'queued': return
        self.update('running')
        self.process.write(encode(self.input)); self.process.closeWriteChannel()

    def read_output(self):
        self.output.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.output)>1048576: self.stop('output_limit')

    def read_error(self):
        self.error_bytes += len(bytes(self.process.readAllStandardError()))
        if self.error_bytes>65536: self.stop('output_limit')

    def finished(self, code, status):
        self.timer.stop(); self.read_output(); self.read_error()
        if self.state not in ('queued','running'): return
        if self.session.closed: return
        if code != 0 or self.error_bytes or status != QtCore.QProcess.NormalExit:
            self.update('failed'); return
        try:
            value = loads(bytes(self.output))
            result_id = review.attach_result(self.session.store,value,self.model,self.input,self.worker_hash)
            self.session.load_result(result_id)
            self.update('succeeded')
        except ValueError:
            self.update('rejected')

    def failed(self, error):
        if self.state in ('queued','running'): self.stop('failed')

    def stop(self, reason):
        if self.state not in ('queued','running'): return
        self.timer.stop(); self.update(reason); self.process.kill()

    def cancel(self):
        self.stop('cancelled')


class ReviewPanel(QtWidgets.QDockWidget):
    def __init__(self, session, parent=None):
        super().__init__('FCST • Thermal Review',parent)
        self.setObjectName('FCSTReviewDock'); self.session=session; self.selected=None
        self.setMinimumWidth(390)
        body=QtWidgets.QWidget(); self.setWidget(body); layout=QtWidgets.QVBoxLayout(body)
        heading=QtWidgets.QLabel('FCST  /  THERMAL REVIEW'); heading.setStyleSheet('font-size:17px;font-weight:600;color:#46b9aa;padding:8px')
        layout.addWidget(heading)
        self.status=QtWidgets.QLabel('Model ready • no current result'); self.status.setObjectName('FCSTValidity'); self.status.setWordWrap(True)
        layout.addWidget(self.status)
        toolbar=QtWidgets.QHBoxLayout()
        for title, name, callback in [('Edit','FCSTEdit',self.edit_selected),('Undo','FCSTUndo',self.undo),('Settings','FCSTSettings',self.edit_settings)]:
            button=QtWidgets.QPushButton(title); button.setObjectName(name); button.clicked.connect(callback); toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.tree=QtWidgets.QTreeWidget(); self.tree.setObjectName('FCSTEntityTree')
        self.tree.setHeaderLabels(['Model / entity','Identity']); self.tree.setMinimumHeight(130)
        self.tree.itemSelectionChanged.connect(self.selection_changed); self.tree.itemDoubleClicked.connect(lambda *_: self.edit_selected())
        layout.addWidget(self.tree,2)
        self.assignments=QtWidgets.QTableWidget(0,3); self.assignments.setObjectName('FCSTAssignments')
        self.assignments.setHorizontalHeaderLabels(['Entity','Mapping','State']); self.assignments.setMaximumHeight(115)
        self.assignments.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.assignments.cellClicked.connect(lambda row,col:self.select_entity(self.assignments.item(row,0).data(QtCore.Qt.UserRole)))
        layout.addWidget(self.assignments)
        self.overlay_mode=QtWidgets.QComboBox(); self.overlay_mode.setObjectName('FCSTOverlay')
        for title,key in [('Temperature contour','temperature'),('Heat flux vectors','heat_flux'),('Surface normals','normals'),('Material axes','material_axes')]:self.overlay_mode.addItem(title,key)
        self.overlay_mode.currentIndexChanged.connect(self.render_spatial)
        layout.addWidget(self.overlay_mode)
        self.cases=QtWidgets.QComboBox(); self.cases.setObjectName('FCSTCase'); self.cases.currentIndexChanged.connect(self.case_changed)
        layout.addWidget(self.cases)
        row=QtWidgets.QHBoxLayout()
        self.run=QtWidgets.QPushButton('Solve'); self.run.setObjectName('FCSTSolve'); self.run.clicked.connect(self.solve)
        self.cancel=QtWidgets.QPushButton('Cancel'); self.cancel.setObjectName('FCSTCancel'); self.cancel.clicked.connect(self.cancel_job)
        row.addWidget(self.run); row.addWidget(self.cancel); layout.addLayout(row)
        self.progress=QtWidgets.QProgressBar(); self.progress.setObjectName('FCSTJobProgress'); self.progress.setRange(0,1); self.progress.setValue(0)
        layout.addWidget(self.progress)
        row=QtWidgets.QHBoxLayout()
        self.unit=QtWidgets.QComboBox(); self.unit.setObjectName('FCSTDisplayUnit'); self.unit.addItems(['K','degC']); self.unit.currentTextChanged.connect(self.render)
        self.time=QtWidgets.QSlider(QtCore.Qt.Horizontal); self.time.setObjectName('FCSTResultTime'); self.time.setRange(0,0); self.time.valueChanged.connect(self.render)
        row.addWidget(self.unit); row.addWidget(self.time,1); layout.addLayout(row)
        self.legend=QtWidgets.QLabel('Temperature / no current data'); self.legend.setObjectName('FCSTContourLegend')
        self.legend.setStyleSheet('padding:7px;color:white;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #243880,stop:0.5 #19a6a3,stop:1 #facc38)')
        layout.addWidget(self.legend)
        self.history=History(); layout.addWidget(self.history,1)
        self.budget=QtWidgets.QPlainTextEdit(); self.budget.setReadOnly(True); self.budget.setObjectName('FCSTEnergyBudget'); self.budget.setMaximumHeight(165)
        layout.addWidget(self.budget)
        self.worker=None; session.on_change=self.refresh; session.panel=self
        self.refresh()

    def refresh(self):
        if self.session.closed: return
        running=self.session.job is not None and self.session.job.state in ('queued','running')
        self.progress.setVisible(running); self.cancel.setEnabled(running)
        self.tree.blockSignals(True); self.cases.blockSignals(True)
        self.tree.clear(); self.cases.clear(); self.cases.addItem('Network • transient',None)
        self.assignments.setRowCount(0)
        groups={}
        for entity in self.session.store.snapshot()['entities']:
            kind=entity['kind']
            if kind not in groups:
                groups[kind]=QtWidgets.QTreeWidgetItem(self.tree,[kind.title()+'s',''])
            item=QtWidgets.QTreeWidgetItem(groups[kind],[entity.get('label') or kind.title(),entity['id'][-8:]])
            item.setData(0,QtCore.Qt.UserRole,entity['id'])
            row=self.assignments.rowCount();self.assignments.insertRow(row)
            obj=self.session.doc.getObject(self.session.objects[entity['id']].Name)
            state=obj.FCSTAttachmentState if obj else 'invalid / missing host object'
            for col,text in enumerate((entity.get('label') or kind.title(),entity['id'][-8:],state)):
                cell=QtWidgets.QTableWidgetItem(text);cell.setData(QtCore.Qt.UserRole,entity['id'])
                if 'invalid' in state or state=='unassigned':cell.setForeground(QtGui.QColor('#d0953b'))
                self.assignments.setItem(row,col,cell)
            if entity['id']==self.selected: item.setSelected(True)
            if kind=='case': self.cases.addItem(entity.get('label') or entity['id'],entity['id'])
        index=self.cases.findData(self.session.case_id); self.cases.setCurrentIndex(max(0,index))
        self.tree.expandAll(); self.tree.resizeColumnToContents(0)
        self.tree.blockSignals(False); self.cases.blockSignals(False)
        if self.session.result is None:
            self.status.setText('Model edited / host dirty • result unavailable or stale')
            self.history.points=[]; self.history.update(); self.budget.clear()
            self.legend.setText('Temperature / no current data'); self.time.setEnabled(False)
        else:
            self.time.setEnabled(True); self.time.setMaximum(len(self.session.result['samples'])-1); self.render()

    def case_changed(self, index):
        self.session.case_id=self.cases.itemData(index)

    def selection_changed(self):
        import FreeCADGui as Gui
        items=self.tree.selectedItems()
        self.selected=items[0].data(0,QtCore.Qt.UserRole) if items else None
        Gui.Selection.clearSelection()
        if self.selected:
            Gui.Selection.addSelection(self.session.objects[self.selected])
        self.render()

    def select_entity(self, entity_id):
        iterator=QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item=iterator.value()
            if item.data(0,QtCore.Qt.UserRole)==entity_id:
                self.tree.setCurrentItem(item); return
            iterator+=1

    def edit_selected(self):
        entity=next((e for e in self.session.store.snapshot()['entities'] if e['id']==self.selected),None)
        if entity:
            dialog=EntityEditor(self.session,entity,self); dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose); dialog.show()

    def edit_settings(self):
        dialog=SettingsEditor(self.session,self); dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose); dialog.show()

    def undo(self):
        try: self.session.undo(); self.refresh()
        except ValueError as e: self.status.setText(diagnostic(e))

    def solve(self):
        if self.session.job and self.session.job.state in ('queued','running'): return
        if not self.worker:
            path,_=QtWidgets.QFileDialog.getOpenFileName(self,'Select the FCST native worker','','Executable (*.exe)')
            if not path: return
            self.worker=path
        try:
            self.session.job=NativeJob(self.session,self.worker)
            self.session.job.changed.connect(self.job_changed)
            self.session.job.start()
        except (ValueError,OSError) as e: self.status.setText(diagnostic(e))

    def job_changed(self,state):
        self.status.setText('Native solve • '+state)
        running=state in ('queued','running')
        self.progress.setVisible(running)
        self.run.setEnabled(not running); self.cancel.setEnabled(running)
        self.progress.setRange(0,0 if running else 1); self.progress.setValue(1 if state=='succeeded' else 0)
        if state=='succeeded': self.refresh()

    def cancel_job(self):
        if self.session.job: self.session.job.cancel()

    def render(self,*_):
        if self.session.spatial_view is not None:
            self.render_spatial()
        if self.session.result is None: return
        try:
            selected=self.selected if self.selected in self.session.result['node_ids'] else None
            value=self.session.show_sample(self.time.value(),selected,self.unit.currentText())
            self.status.setText('CURRENT • native result • t = '+format(value['time_s'],'.6g')+' s')
            self.legend.setText(f"{value['lower']:.4g} — {value['upper']:.4g} {value['unit']}  /  fixed scale")
            self.history.points=value['history']; self.history.unit=value['unit']; self.history.update()
            lines=['HEAT FLOW / W  •  canonical node order']
            lines += [k.replace('_',' ')+': '+', '.join(format(v,'.5g') for v in values) for k,values in value['powers'].items()]
            lines += ['ENERGY / J',json.dumps(value['energy'],sort_keys=True),'HEATER DUTY / fraction',json.dumps(value['duty'],sort_keys=True)]
            self.budget.setPlainText('\n'.join(lines))
        except ValueError as e:
            self.session.clear_display(); self.refresh(); self.status.setText(diagnostic(e))

    def render_spatial(self,*_):
        if self.session.spatial_view is None:return
        try:
            value=self.session.spatial_view.show(self.overlay_mode.currentData(),min(self.time.value(),len(self.session.spatial_view.value['times'])-1))
            self.budget.setPlainText(json.dumps(value,indent=2))
        except ValueError as e:self.status.setText(diagnostic(e))
