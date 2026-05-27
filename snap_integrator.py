# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressDialog, QListWidget, QListWidgetItem,
    QCheckBox
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProject, QgsGeometry, QgsFeature, QgsPointXY,
    QgsVectorLayer, QgsField, QgsWkbTypes
)
from PyQt5.QtCore import QVariant
import os


class SnapIntegratorDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snap Integrator")
        self.setMinimumWidth(480)

        layout = QVBoxLayout()

        self.use_boundary_checkbox = QCheckBox("Use selected boundary filter")
        self.use_boundary_checkbox.setChecked(False)

        self.poly_combo = QComboBox()
        self.line_combo = QComboBox()

        self.compare_fields_list = QListWidget()
        self.compare_fields_list.setSelectionMode(QListWidget.MultiSelection)

        self.exclude_fields_list = QListWidget()
        self.exclude_fields_list.setSelectionMode(QListWidget.MultiSelection)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("All shared endpoints", "all")
        self.mode_combo.addItem("Different in selected fields", "different_selected_fields")
        self.mode_combo.addItem("Same values in selected fields", "same_selected_fields")
        self.mode_combo.addItem("Same values in ALL fields", "same_all_fields")
        self.mode_combo.addItem(
            "All endpoints except differences in excluded fields",
            "all_except_excluded_differences"
        )

        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.VectorLayer:
                if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.poly_combo.addItem(layer.name(), layer)
                elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                    self.line_combo.addItem(layer.name(), layer)

        self.line_combo.currentIndexChanged.connect(self.updateFieldsLists)
        self.updateFieldsLists()

        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)

        layout.addWidget(self.use_boundary_checkbox)
        layout.addWidget(QLabel("Boundary layer:"))
        layout.addWidget(self.poly_combo)
        layout.addWidget(QLabel("Line layer Roads:"))
        layout.addWidget(self.line_combo)
        layout.addWidget(QLabel("Fields to compare:"))
        layout.addWidget(self.compare_fields_list)
        layout.addWidget(QLabel("Fields to exclude/check for exclusion:"))
        layout.addWidget(self.exclude_fields_list)
        layout.addWidget(QLabel("Filter mode:"))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.ok_button)

        self.setLayout(layout)

    def updateFieldsLists(self):
        self.compare_fields_list.clear()
        self.exclude_fields_list.clear()

        line_layer = self.line_combo.currentData()
        if not line_layer:
            return

        for field in line_layer.fields():
            item_compare = QListWidgetItem(field.name())
            item_compare.setData(Qt.UserRole, field.name())
            self.compare_fields_list.addItem(item_compare)

            item_exclude = QListWidgetItem(field.name())
            item_exclude.setData(Qt.UserRole, field.name())
            self.exclude_fields_list.addItem(item_exclude)

    def selectedCompareFields(self):
        return [item.data(Qt.UserRole) for item in self.compare_fields_list.selectedItems()]

    def selectedExcludeFields(self):
        return [item.data(Qt.UserRole) for item in self.exclude_fields_list.selectedItems()]

    def getInputs(self):
        return (
            self.use_boundary_checkbox.isChecked(),
            self.poly_combo.currentData(),
            self.line_combo.currentData(),
            self.selectedCompareFields(),
            self.selectedExcludeFields(),
            self.mode_combo.currentData()
        )


class SnapIntegrator:

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
        dialog.ok_button.clicked.connect(dialog.accept)
        dialog.accepted.connect(lambda: self.process(dialog))
        dialog.exec_()

    def clean_value(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def process(self, dialog):
        use_boundary, poly_layer, line_layer, compare_fields, exclude_fields, mode = dialog.getInputs()

        if not line_layer:
            self.iface.messageBar().pushWarning(
                "SnapIntegrator", "Please select a line layer."
            )
            return

        if mode in ("different_selected_fields", "same_selected_fields") and not compare_fields:
            self.iface.messageBar().pushWarning(
                "SnapIntegrator", "Please select one or more fields to compare."
            )
            return

        if mode == "all_except_excluded_differences" and not exclude_fields:
            self.iface.messageBar().pushWarning(
                "SnapIntegrator", "Please select one or more excluded fields."
            )
            return

        boundary_geom = None
        inner_boundary = None

        if use_boundary:
            if not poly_layer:
                self.iface.messageBar().pushWarning(
                    "SnapIntegrator", "Boundary checkbox is ON. Please select a boundary layer."
                )
                return

            selected_polys = poly_layer.selectedFeatures()

            if len(selected_polys) < 1:
                self.iface.messageBar().pushWarning(
                    "SnapIntegrator", "Boundary checkbox is ON. Please select at least one polygon."
                )
                return

            valid_geoms = [
                feat.geometry()
                for feat in selected_polys
                if feat.geometry() is not None and not feat.geometry().isEmpty()
            ]

            if not valid_geoms:
                self.iface.messageBar().pushWarning(
                    "SnapIntegrator", "Selected boundary polygons have no valid geometry."
                )
                return

            boundary_geom = QgsGeometry.unaryUnion(valid_geoms)

            if boundary_geom is None or boundary_geom.isEmpty():
                self.iface.messageBar().pushWarning(
                    "SnapIntegrator", "Selected boundary polygons could not be combined."
                )
                return

            inner_boundary = boundary_geom.buffer(-0.0001, 1)

        progress = QProgressDialog(
            "Processing...",
            "Cancel",
            0,
            line_layer.featureCount() + 1,
            self.iface.mainWindow()
        )
        progress.setWindowTitle("Snap Integrator")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        endpoint_map = {}
        feat_by_id = {}
        current_step = 0

        for feat in line_layer.getFeatures():
            geom = feat.geometry()

            if geom is not None and not geom.isEmpty():
                feat_by_id[feat.id()] = feat

                parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]

                for part in parts:
                    if len(part) < 2:
                        continue

                    if part[0].x() == part[-1].x() and part[0].y() == part[-1].y():
                        continue

                    start_pt = (round(part[0].x(), 6), round(part[0].y(), 6))
                    end_pt = (round(part[-1].x(), 6), round(part[-1].y(), 6))

                    endpoint_map.setdefault(start_pt, set()).add(feat.id())
                    endpoint_map.setdefault(end_pt, set()).add(feat.id())

            current_step += 1
            progress.setValue(current_step)

            if progress.wasCanceled():
                progress.close()
                return

        crs = line_layer.crs().authid()

        result_layer = QgsVectorLayer(
            f"Point?crs={crs}",
            "SnapIntegrator_Points",
            "memory"
        )

        provider = result_layer.dataProvider()

        output_fields = [
            QgsField("id", QVariant.Int),
            QgsField("mode", QVariant.String),
            QgsField("boundary", QVariant.String),
            QgsField("fid1", QVariant.Int),
            QgsField("fid2", QVariant.Int),
            QgsField("diff_fields", QVariant.String),
            QgsField("same_fields", QVariant.String),
            QgsField("diff_values", QVariant.String),
            QgsField("same_values", QVariant.String),
            QgsField("excluded_diff", QVariant.String),
            QgsField("excluded_values", QVariant.String),
        ]

        provider.addAttributes(output_fields)
        result_layer.updateFields()

        new_features = []
        idx = 1

        for (x, y), fids in endpoint_map.items():

            if len(fids) != 2:
                continue

            fid_list = sorted(list(fids))
            fid1 = fid_list[0]
            fid2 = fid_list[1]

            feat1 = feat_by_id.get(fid1)
            feat2 = feat_by_id.get(fid2)

            if feat1 is None or feat2 is None:
                continue

            diff_fields = []
            same_fields = []
            diff_values = []
            same_values = []
            excluded_diff_fields = []
            excluded_values = []

            if mode in ("different_selected_fields", "same_selected_fields"):
                fields_to_check = compare_fields
            else:
                fields_to_check = [field.name() for field in line_layer.fields()]

            for field_name in fields_to_check:
                value1 = self.clean_value(feat1[field_name])
                value2 = self.clean_value(feat2[field_name])

                if value1 == value2:
                    same_fields.append(field_name)
                    same_values.append(f"{field_name}: {value1}")
                else:
                    diff_fields.append(field_name)
                    diff_values.append(f"{field_name}: {value1} <> {value2}")

            if mode == "different_selected_fields":
                if len(diff_fields) == 0:
                    continue

            elif mode == "same_selected_fields":
                if len(diff_fields) > 0:
                    continue

            elif mode == "same_all_fields":
                if len(diff_fields) > 0:
                    continue

            elif mode == "all_except_excluded_differences":
                for field_name in exclude_fields:
                    value1 = self.clean_value(feat1[field_name])
                    value2 = self.clean_value(feat2[field_name])

                    if value1 != value2:
                        excluded_diff_fields.append(field_name)
                        excluded_values.append(f"{field_name}: {value1} <> {value2}")

                if len(excluded_diff_fields) > 0:
                    continue

            pt_geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))

            if use_boundary:
                if inner_boundary is not None and not inner_boundary.isEmpty():
                    if not pt_geom.within(inner_boundary):
                        continue
                else:
                    if not pt_geom.within(boundary_geom):
                        continue

            new_feat = QgsFeature(result_layer.fields())
            new_feat.setGeometry(pt_geom)

            new_feat["id"] = idx
            new_feat["mode"] = mode
            new_feat["boundary"] = "ON" if use_boundary else "OFF"
            new_feat["fid1"] = fid1
            new_feat["fid2"] = fid2
            new_feat["diff_fields"] = ", ".join(diff_fields)
            new_feat["same_fields"] = ", ".join(same_fields)
            new_feat["diff_values"] = " | ".join(diff_values)
            new_feat["same_values"] = " | ".join(same_values)
            new_feat["excluded_diff"] = ", ".join(excluded_diff_fields)
            new_feat["excluded_values"] = " | ".join(excluded_values)

            new_features.append(new_feat)
            idx += 1

        progress.close()

        if not new_features:
            self.iface.messageBar().pushInfo(
                "SnapIntegrator", "No matching endpoints found."
            )
            return

        provider.addFeatures(new_features)
        result_layer.updateExtents()
        QgsProject.instance().addMapLayer(result_layer)

        self.iface.messageBar().pushSuccess(
            "SnapIntegrator",
            f"Exported {len(new_features)} point(s). Boundary filter: {'ON' if use_boundary else 'OFF'}."
        )