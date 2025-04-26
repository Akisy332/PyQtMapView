from PyQt5.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItemGroup, QPushButton
from PyQt5.QtGui import QPixmap, QColor, QImage, QPainter, QIcon
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal, QSize, QPoint, pyqtSlot
from PyQt5.QtWidgets import QMenu, QMessageBox
from PyQt5.QtCore import qSetMessagePattern

import os
import sys
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mapView import PyQtMapView


class MapButtons:
    def __init__(self, mapView: "PyQtMapView",
                 zoomIn: bool = True,
                 zoomOut: bool = True,
                 layers: bool = True):
        self.mapView = mapView
        
        # buttons
        self.buttonZoomIn = None
        self.buttonZoomOut = None
        self.buttonLayers = None
        
        self.add_buttons(zoomIn, zoomOut, layers)
    
    def add_buttons(self, zoomIn: bool = True, zoomOut: bool = True, layers: bool = True):
        if zoomIn is True:
            self.buttonZoomIn = QPushButton("+", self.mapView)
            self.buttonZoomIn.setGeometry(20, 20, 29, 29)
            self.buttonZoomIn.clicked.connect(self.zoomIn)
        if zoomOut is True:    
            self.buttonZoomOut = QPushButton("-", self.mapView)
            self.buttonZoomOut.setGeometry(20, 60, 29, 29)
            self.buttonZoomOut.clicked.connect(self.zoomOut)
        if layers is True:
            current_path = os.path.dirname(os.path.abspath(__file__))
            image_path = os.path.join(current_path, 'icon-layers.png')
            self.icon = QImage(image_path)
            buttonLayers_icon = QPixmap.fromImage(self.icon)
            self.buttonLayers = QPushButton("", self.mapView)

            self.buttonLayers.setGeometry(self.mapView.size().width() - 55, 20, 35, 35)
            self.buttonLayers.setIcon(QIcon(buttonLayers_icon))
            self.buttonLayers.setIconSize(QSize(30, 30))
            self.buttonLayers.clicked.connect(self.change_layers)
    
    def zoomIn(self):
        self.mapView.set_zoom(self.mapView.zoom + 1)
    
    def zoomOut(self):
        self.mapView.set_zoom(self.mapView.zoom - 1)
    
    def change_layers(self):
        # Создаем меню для выбора слоев
        menu = QMenu(self.mapView)
        for name in self.mapView.map_layers:
            menu.addAction(name.get('name_map'), self.select_layer)
        
        global_pos = self.buttonLayers.mapToGlobal(self.buttonLayers.rect().bottomRight())
        menu.exec_(QPoint(global_pos.x() - menu.sizeHint().width(), global_pos.y()))

    def select_layer(self):
        for name in self.mapView.map_layers:
            if name.get('name_map') == self.mapView.sender().text():
                self.mapView.set_tile_server(name.get('name_map')) 