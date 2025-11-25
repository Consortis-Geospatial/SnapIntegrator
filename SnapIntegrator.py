from qgis.PyQt.QtCore import Qt  
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
    """Dialog for selecting layers"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snap Integrator")
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        self.poly_label = QLabel("Select Polygon Layer (Boundary):")
        self.poly_combo = QComboBox()
        self.line_label = QLabel("Select Line Layer:")
        self.line_combo = QComboBox()

        # Populate combos with layers
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.VectorLayer:
                if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.poly_combo.addItem(layer.name(), layer)
                elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                    self.line_combo.addItem(layer.name(), layer)

        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)

        layout.addWidget(self.poly_label)
        layout.addWidget(self.poly_combo)
        layout.addWidget(self.line_label)
        layout.addWidget(self.line_combo)
        layout.addWidget(self.ok_button)

        self.setLayout(layout)

    def getLayers(self):
        poly_layer = self.poly_combo.currentData()
        line_layer = self.line_combo.currentData()
        return poly_layer, line_layer


class SnapIntegrator:
    """Main SnapIntegrator plugin"""

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.action = None

    def initGui(self):
        """Add toolbar button and menu item"""
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")

        self.action = QAction(QIcon(icon_path), "Snap Integrator", self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Snap Integrator", self.action)

    def unload(self):
        """Remove toolbar button and menu item"""
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&Snap Integrator", self.action)

    def run(self):
        """Show the dialog"""
        dialog = SnapIntegratorDialog()
        dialog.ok_button.clicked.connect(lambda: self.process(dialog))
        dialog.exec_()

    def process(self, dialog):
        poly_layer, line_layer = dialog.getLayers()
        if not poly_layer or not line_layer:
            self.iface.messageBar().pushWarning("SnapIntegrator", "Please select both layers.")
            return

        selected_polys = poly_layer.selectedFeatures()
        if len(selected_polys) != 1:
            self.iface.messageBar().pushWarning("SnapIntegrator", "Please select exactly one polygon feature.")
            return

        boundary_geom = selected_polys[0].geometry()

        # Collect endpoints
        endpoint_map = {}
        line_geoms = {}
        for feat in line_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            line_geoms[feat.id()] = geom

            if geom.isMultipart():
                parts = geom.asMultiPolyline()
            else:
                parts = [geom.asPolyline()]

            for part in parts:
                if len(part) < 2:
                    continue

                # 🔴 FIX 1: Exclude closed lines (start = end)
                if part[0].x() == part[-1].x() and part[0].y() == part[-1].y():
                    continue

                start_pt = (round(part[0].x(), 6), round(part[0].y(), 6))
                end_pt = (round(part[-1].x(), 6), round(part[-1].y(), 6))

                for pt in [start_pt, end_pt]:
                    endpoint_map.setdefault(pt, set()).add(feat.id())

        # Keep only endpoints shared by exactly 2 lines
        merge_candidates = []
        tolerance = 0.0001  # adjust depending on CRS (meters if projected, degrees if geographic)
        for (x, y), fids in endpoint_map.items():
            if len(fids) == 2:  # exactly 2 lines share this point
                pt = QgsPointXY(x, y)
                pt_geom = QgsGeometry.fromPointXY(pt)

                # 🔴 FIX 2: Must be strictly inside polygon (not on boundary)
                inner_boundary = boundary_geom.buffer(-tolerance, 1)
                if not pt_geom.within(inner_boundary):
                    continue

                merge_candidates.append(pt_geom)

        if not merge_candidates:
            self.iface.messageBar().pushInfo("SnapIntegrator", "No candidate endpoints found inside selected polygon.")
            dialog.close()
            return

        # Export results to a memory point layer
        crs = line_layer.crs().authid()
        result_layer = QgsVectorLayer(f"Point?crs={crs}", "SnapIntegrator_Points", "memory")
        prov = result_layer.dataProvider()

        prov.addAttributes([QgsField("id", QVariant.Int)])
        result_layer.updateFields()

        new_feats = []
        for i, pt_geom in enumerate(merge_candidates):
            new_feat = QgsFeature(result_layer.fields())
            new_feat.setGeometry(pt_geom)
            new_feat.setAttribute("id", i + 1)
            new_feats.append(new_feat)

        prov.addFeatures(new_feats)
        result_layer.updateExtents()

        QgsProject.instance().addMapLayer(result_layer)
        self.iface.messageBar().pushSuccess("SnapIntegrator", f"Exported {len(new_feats)} candidate point(s).")

        dialog.close()
