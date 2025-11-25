# -*- coding: utf-8 -*-

from qgis.PyQt.QtWidgets import QAction, QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton
from qgis.PyQt.QtGui import QIcon

from qgis.core import (
    QgsProject,
    QgsGeometry,
    QgsFeature,
    QgsPointXY,
    QgsVectorLayer,
    QgsField,
    QgsWkbTypes
)
from qgis.utils import iface
from PyQt5.QtCore import QVariant
import os


class SnapIntegratorDialog(QDialog):
    """Dialog for selecting layers and optional field"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snap Integrator")
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        self.poly_label = QLabel("Select Polygon Layer (Boundary):")
        self.poly_combo = QComboBox()

        self.line_label = QLabel("Select Line Layer (Roads):")
        self.line_combo = QComboBox()

        self.field_label = QLabel("Select Road Attribute Field (optional):")
        self.field_combo = QComboBox()

        # Populate layer combos
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.VectorLayer:
                if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.poly_combo.addItem(layer.name(), layer)
                elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                    self.line_combo.addItem(layer.name(), layer)

        # Update field combo when line layer changes
        self.line_combo.currentIndexChanged.connect(self.updateFieldCombo)
        self.updateFieldCombo()

        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)

        layout.addWidget(self.poly_label)
        layout.addWidget(self.poly_combo)
        layout.addWidget(self.line_label)
        layout.addWidget(self.line_combo)
        layout.addWidget(self.field_label)
        layout.addWidget(self.field_combo)
        layout.addWidget(self.ok_button)

        self.setLayout(layout)

    def updateFieldCombo(self):
        """Populate field combo based on selected line layer"""
        self.field_combo.clear()
        self.field_combo.addItem("<no field filter>", None)

        line_layer = self.line_combo.currentData()
        if not line_layer:
            return

        for field in line_layer.fields():
            self.field_combo.addItem(field.name(), field.name())

    def getLayersAndField(self):
        poly_layer = self.poly_combo.currentData()
        line_layer = self.line_combo.currentData()
        field_name = self.field_combo.currentData()
        return poly_layer, line_layer, field_name


class SnapIntegrator:
    """Main SnapIntegrator plugin"""

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.action = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        self.action = QAction(QIcon(icon_path), "Snap Integrator", self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Snap Integrator", self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&Snap Integrator", self.action)

    def run(self):
        dialog = SnapIntegratorDialog()
        dialog.ok_button.clicked.connect(lambda: self.process(dialog))
        dialog.exec_()

    def process(self, dialog):
        poly_layer, line_layer, field_name = dialog.getLayersAndField()

        if not poly_layer or not line_layer:
            self.iface.messageBar().pushWarning(
                "SnapIntegrator", "Please select both polygon and line layers."
            )
            return

        if field_name is not None:
            if line_layer.fields().indexOf(field_name) == -1:
                self.iface.messageBar().pushWarning(
                    "SnapIntegrator", f"Field '{field_name}' not found in line layer."
                )
                return

        selected_polys = poly_layer.selectedFeatures()
        if len(selected_polys) != 1:
            self.iface.messageBar().pushWarning(
                "SnapIntegrator", "Please select exactly one polygon feature in the boundary layer."
            )
            return

        boundary_geom = selected_polys[0].geometry()
        if boundary_geom is None or boundary_geom.isEmpty():
            self.iface.messageBar().pushWarning(
                "SnapIntegrator", "Selected polygon has no valid geometry."
            )
            return

        # Collect endpoints
        endpoint_map = {}
        for feat in line_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            if geom.isMultipart():
                parts = geom.asMultiPolyline()
            else:
                parts = [geom.asPolyline()]

            for part in parts:
                if len(part) < 2:
                    continue
                if part[0].x() == part[-1].x() and part[0].y() == part[-1].y():
                    continue
                start_pt = (round(part[0].x(), 6), round(part[0].y(), 6))
                end_pt = (round(part[-1].x(), 6), round(part[-1].y(), 6))
                for pt in (start_pt, end_pt):
                    endpoint_map.setdefault(pt, set()).add(feat.id())

        feat_by_id = {f.id(): f for f in line_layer.getFeatures()}
        tolerance = 0.0001

        crs = line_layer.crs().authid()
        result_layer = QgsVectorLayer("Point?crs={}".format(crs), "SnapIntegrator_Points", "memory")
        prov = result_layer.dataProvider()

        # Attributes
        fields = [QgsField("id", QVariant.Int)]
        if field_name is not None:
            fields.extend([
                QgsField("field", QVariant.String),
                QgsField("val1", QVariant.String),
                QgsField("val2", QVariant.String),
            ])
        prov.addAttributes(fields)
        result_layer.updateFields()

        new_feats = []
        idx = 1

        for (x, y), fids in endpoint_map.items():
            if len(fids) != 2:
                continue

            fid1, fid2 = list(fids)
            feat1 = feat_by_id.get(fid1)
            feat2 = feat_by_id.get(fid2)
            if feat1 is None or feat2 is None:
                continue

            if field_name is not None:
                val1 = feat1[field_name]
                val2 = feat2[field_name]
                if val1 == val2:
                    continue

            pt = QgsPointXY(x, y)
            pt_geom = QgsGeometry.fromPointXY(pt)

            inner_boundary = boundary_geom.buffer(-tolerance, 1)
            if inner_boundary is None or inner_boundary.isEmpty():
                if not pt_geom.within(boundary_geom):
                    continue
            else:
                if not pt_geom.within(inner_boundary):
                    continue

            new_feat = QgsFeature(result_layer.fields())
            new_feat.setGeometry(pt_geom)
            new_feat["id"] = idx

            if field_name is not None:
                new_feat["field"] = field_name
                new_feat["val1"] = str(val1)
                new_feat["val2"] = str(val2)

            new_feats.append(new_feat)
            idx += 1

        if not new_feats:
            msg = "No candidate endpoints found inside the selected polygon."
            if field_name is not None:
                msg += " (with differing field values)."
            self.iface.messageBar().pushInfo("SnapIntegrator", msg)
            dialog.close()
            return

        prov.addFeatures(new_feats)
        result_layer.updateExtents()
        QgsProject.instance().addMapLayer(result_layer)

        msg = "Exported {} candidate point(s)".format(len(new_feats))
        if field_name is not None:
            msg += " (with differing values in '{}')".format(field_name)
        self.iface.messageBar().pushSuccess("SnapIntegrator", msg)

        dialog.close()
