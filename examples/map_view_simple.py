import sys
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget, QMainWindow

from PyQtMapView import PyQtMapView, Path
# from PyQtMapView import *

class Map:
    def __init__(self):
        # create map widget
        self.mapView = PyQtMapView()

        # set other tile server (standard is OpenStreetMap)
        # self.mapView.set_tile_server("https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)  # google normal
        # self.mapView.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)  # google satellite

        # set current position and zoom
        self.mapView.set_position(52.516268, 13.377695, marker=False)  # Berlin, Germany
        self.mapView.set_zoom(17)
        self.mapView.addTileServer("black and white", "BlackAndWhite", "http://a.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", 512)
        # set current position with address
        # self.mapView.set_address("Berlin Germany", marker=False)

        # set a position marker (also with a custom color and command on click)
        marker_2 = self.mapView.set_marker(52.516268, 13.377695, text="Brandenburger Tor", command=self.marker_click)
        marker_3 = self.mapView.set_marker(52.55, 13.4, text="52.55, 13.4")
        # marker_3.setPosition(...)
        # marker_3.setText(...)
        # marker_3.delete()

        # set a path
        path_1 = Path(self.mapView, marker_2.position, [(marker_3.position, "#FF0000"), (52.568, 13.4), (52.569, 13.35)])
        # path_1.addPosition(...)
        # path_1.removePosition(...)
        # path_1.delete()
    
    def marker_click(self, marker):
        print(f"marker clicked - text: {marker.text}  position: {marker.position}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("map_view_simple_example.py")
        self.resize(800, 700)
        
        # Создаем центральный виджет и устанавливаем компоновщик
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Инициализируем класс карты
        map = Map()
        
        # Добавляем QGraphicsView с картой
        layout.addWidget(map.mapView)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())