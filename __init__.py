# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SnapIntegrator
                                 A QGIS plugin
 Finds unmerged road endpoints inside a boundary polygon, optionally based on a field
                              -------------------
        begin                : 2025-01-01
 ***************************************************************************/
"""

from __future__ import absolute_import


def classFactory(iface):
    """
    Load SnapIntegrator class from file snap_integrator.py

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .snap_integrator import SnapIntegrator
    return SnapIntegrator(iface)
