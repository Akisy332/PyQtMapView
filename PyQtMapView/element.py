import os
from PyQt5.QtWidgets import QApplication, QGraphicsPixmapItem, QPushButton, QGraphicsLineItem, QGraphicsTextItem, QMenu, QMessageBox
from PyQt5.QtGui import QPixmap, QColor, QImage, QPainter, QIcon, QPen, QCursor, QFont
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal, QSize, QPoint, pyqtSlot

from .utility_functions import decimal_to_osm, osm_to_decimal

from typing import TYPE_CHECKING, Callable
if TYPE_CHECKING:
    from .mapView import PyQtMapView


class Tile:
    def __init__(self, mapView: "PyQtMapView", image, tile_name_position):
        self.mapView = mapView
        self.image = image
        self.tile_name_position = tile_name_position
        
        self.pixmap_item = None

        self.canvas_object = None
        self.widget_tile_width = 0
        self.widget_tile_height = 0

    def __del__(self):
        # if Tile object gets garbage collected or deleted, delete image from canvas
        self.delete()

    def set_image_and_position(self, image, tile_name_position):
        self.image = image
        self.tile_name_position = tile_name_position
        self.draw(image_update=True)

    def setImage(self, image):
        self.image = image
        self.draw(image_update=True)

    def get_canvas_pos(self):
        self.widget_tile_width = self.mapView.lowerRightTilePos[0] - self.mapView.upperLeftTilePos[0]
        self.widget_tile_height = self.mapView.lowerRightTilePos[1] - self.mapView.upperLeftTilePos[1]
        
        canvas_pos_x = ((self.tile_name_position[0] - self.mapView.upperLeftTilePos[
            0]) / self.widget_tile_width) * self.mapView._width
        canvas_pos_y = ((self.tile_name_position[1] - self.mapView.upperLeftTilePos[
            1]) / self.widget_tile_height) * self.mapView._height
        
        return canvas_pos_x, canvas_pos_y

    def delete(self):
        try:
            if not self.pixmap_item == None:
                if self.pixmap_item in self.mapView.mapScene.items():
                    self.mapView.mapScene.removeItem(self.pixmap_item)
            self.canvas_object = None
        except Exception:
            pass

    def draw(self, image_update=False):
        canvas_pos_x, canvas_pos_y = self.get_canvas_pos()
        
        if self.canvas_object is None:
            if not (self.image == self.mapView.tileManager.notLoadedTileImage or self.image == self.mapView.tileManager.emptyTileImage):
                self.canvas_object = self.mapView.tile_group
                self.pixmap_item = QGraphicsPixmapItem(self.image)
                self.pixmap_item.setPos(canvas_pos_x, canvas_pos_y)
                self.canvas_object.addToGroup(self.pixmap_item)  
        else:
            self.pixmap_item.setPos(canvas_pos_x, canvas_pos_y)

            if image_update:
                if not (self.image == self.mapView.tileManager.notLoadedTileImage or self.image == self.mapView.tileManager.emptyTileImage):
                    self.pixmap_item.setPixmap(self.image)
                else:
                    if not self.pixmap_item == None:
                        self.mapView.mapScene.removeItem(self.pixmap_item)
                    self.canvas_object = None
                    


class Marker(QGraphicsPixmapItem):
    def __init__(self,
                 mapView: "PyQtMapView",
                 position: tuple,
                 text: str = None,
                 textColor: str = "#652A22",
                 font: QFont = "Tahoma 11 bold",
                 markerColorCircle: str = "#000000",
                 markerColorOutside: str = "#FF0000",
                 command: Callable = None,
                 image: QImage = None,
                 imageHeight = None,
                 imageWidth = None,
                 icon: QImage = None,
                 iconHeight = None,
                 iconWidth = None,
                 imageZoomVisibility: tuple = (0, float("inf"))):
        super().__init__()
        self.mapView = mapView
        self.position = position
        self.image = image
        self.icon = icon
        
        self.imageZoomVisibility = imageZoomVisibility
        self.command = command
        
        self.imageVisible = False
        self.markerVisible = True
        
        self.itemText = None
        
        # Переделать создание иконки маркера
        if self.icon is None:
            # Убрать в другое место, ибо каждый новый маркер опять сохраняет изображение в память
            currentPath = os.path.dirname(os.path.abspath(__file__))
            imagePath = os.path.join(currentPath, 'marker.png') 
            
            self.icon = QImage(imagePath)
            if self.icon.isNull():
                print("Failed to load marker image:", imagePath)
            else:
                iconWidth = self.icon.width() // 2
                iconHeight = self.icon.height() // 2
            self.icon = self.__imageFromPixmap(self.icon, iconWidth, iconHeight)
            
            colors = (QColor("#FF0000"), QColor(markerColorOutside), QColor("#000000"), QColor(markerColorCircle))
            if markerColorCircle  != "#000000" or markerColorOutside != "#FF0000":
                self.changeLolorMarker(colors)
        else:
            self.icon = self.__imageFromPixmap(self.icon, iconWidth, iconHeight)
        
        # пофиксить курсор над текстом
        self.setAcceptHoverEvents(True)
        
        self.setOffset(-self.icon.rect().width()/2, -self.icon.rect().height())
        self.setPixmap(self.icon)
        
        self.mapView.canvas_marker_list.append(self)
        
        self.mapView.mapScene.addItem(self)
        self.setZValue(3)
        
        #пофикисить исчезание текста при смене карты и смене видимости
        self.text = text
        if text is not None:
            self.setText(text, textColor, font)
        
        self.draw()
        
    def __imageFromPixmap(self, image: QImage, width: int = None, height: int = None) -> QPixmap:
        if width is None:
            width = image.width()
        if height is None:
            height = image.height()
        image = image.scaled(width, height)
        image = QPixmap.fromImage(image)
        return image
    
    def changeLolorMarker(self, colors: list = [QColor]):        
    # colors: the first element is the old color, the second is the new color, etc.  
    # the colors of the initial marker: markerColorOutside = #FF0000", markerColorCircle = #000000 
        image = self.icon.toImage()        
        for x in range(image.width()):            
            for y in range(image.height()):                
                pixelColor = image.pixelColor(x, y)                
                if pixelColor.alpha() > 0:  # если пиксель не прозрачный                    
                    for idx, newPixelColor in enumerate(colors):                        
                        if newPixelColor == pixelColor and idx % 2 == 0:                        
                            # Изменяем цвет на новый
                            new_color = colors[idx + 1]  # Получаем следующий (новый) цвет
                            # Устанавливаем новый цвет
                            pixelColor.setRgb(new_color.red(), new_color.green(), new_color.blue())
                            break
                    image.setPixelColor(x, y, pixelColor)        
        self.icon = self.__imageFromPixmap(image)

    def delete(self):
        self.mapView.canvas_marker_list.remove(self)
        self.mapView.mapScene.removeItem(self)

    def setPosition(self, deg_x, deg_y):
        self.position = (deg_x, deg_y)
        self.draw()

    def __textOffset(self):
        textOffsetY = self.icon.rect().height() + 20 if self.icon is not None else 70
        textOffsetX = self.itemText.boundingRect().width() / 2
        return textOffsetX, textOffsetY
    
    def setText(self, text, textColor: str = "#652A22", font: QFont = "Tahoma 11 bold"):
        self.text = text
        if self.itemText is None:
            self.itemText = QGraphicsTextItem(text, self)
        else:
            self.itemText.setPlainText(text)
        self.itemText.setFont(QFont(font, 12)) 
        self.itemText.setDefaultTextColor(QColor(textColor)) 
        textOffsetX, textOffsetY = self.__textOffset()
        self.itemText.setPos(-textOffsetX, -textOffsetY)
        self.draw()

    # debug
    def setIcon(self, new_icon: QImage, width: int = None, height: int = None):
        self.icon = self.__imageFromPixmap(new_icon, width, height)
        self.setPixmap(self.icon)
        self.setOffset(-self.icon.rect().width()/2, -self.icon.rect().height())
        textOffsetX, textOffsetY = self.__textOffset()
        self.itemText.setPos(-textOffsetX, -textOffsetY)
        self.draw()

    def setVisibleImage(self, visible: bool):
        self.imageVisible = visible
        self.draw()

    def setVisibleMarker(self, visible: bool):
        self.markerVisible = visible
        self.draw()

    def hoverEnterEvent(self, event):
        if self.command != None and self.markerVisible == True:
            QApplication.setOverrideCursor(QCursor(Qt.PointingHandCursor))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.command != None and self.markerVisible == True:
            QApplication.restoreOverrideCursor()
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        if self.command is not None:
            self.command(self)
        super().mousePressEvent(event)
    
    def __getCanvasPos(self, position):
        tilePosition = decimal_to_osm(*position, round(self.mapView.zoom))

        widgetTileWidth = self.mapView.lowerRightTilePos[0] - self.mapView.upperLeftTilePos[0]
        widgetTileHeight = self.mapView.lowerRightTilePos[1] - self.mapView.upperLeftTilePos[1]

        canvasPosX = ((tilePosition[0] - self.mapView.upperLeftTilePos[0]) / widgetTileWidth) * self.mapView._width
        canvasPosY = ((tilePosition[1] - self.mapView.upperLeftTilePos[1]) / widgetTileHeight) * self.mapView._height

        return canvasPosX, canvasPosY
    
    def draw(self, event=None):
        canvasPosX, canvasPosY = self.__getCanvasPos(self.position)

        if 0 - 50 < canvasPosX < self.mapView._width + 50 and 0 < canvasPosY < self.mapView._height + 70:
            # draw icon image for marker
            self.setPos(canvasPosX, canvasPosY)
            self.setVisible(self.markerVisible)
        else:
            self.setVisible(False)



class Buttons:
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
                
            

class Path(QGraphicsLineItem):
    def __init__(self,
                 mapView: "PyQtMapView",
                 startPosition: tuple,
                 positionList: list[tuple],
                 color: str = "#3E69CB",
                 command: Callable = None,
                 namePath: str = None,
                 widthLine: int = 9):
        super().__init__()
        self.mapView = mapView
        self.pathColor = color
        self.command = command
        self.widthLine = widthLine
        self.namePath = namePath
        
        self.pathVisible = True
        
        self.__positionList = []
        self.__positionList.append((startPosition, None))
        for item in positionList:
            if isinstance(item[0], tuple):
                self.__positionList.append((item[0], item[1]))
            else:    
                self.__positionList.append((item, self.pathColor))
        
        self.__segments = 0
        self.__canvasLinePositions = []
        self.__canvasLine: list[tuple[QGraphicsLineItem, QColor]] = []
        self.__lastUpperLeftTilePos = None
        self.__lastPositionListLength = len(self.__positionList)
        
        self.mapView.PathList.append(self)
        self.mapView.mapScene.addItem(self)
        self.setZValue(1)
        self.draw()

    # User methods
    def getSegments(self) -> int:
        """Returns the number of path segments."""
        return self.__segments
    
    def updateColorLine(self, segment: int, color: str):
        """Changing the color of a path segment.
 
        :param segment:
        :type segment: Segment number from 0
        :param color:
        :type color: HEX color code
        """
        if segment >= self.__segments:
            segment = self.__segments - 1
        elif segment < 0:
            segment = 0
        item = list(self.__canvasLine[segment])
        item[1] = QColor(color)
        self.__canvasLine[segment] = tuple(item)
        self.draw()
        
    def delete(self):
        """Deleting a path. """
        self.mapView.PathList.remove(self)
        self.mapView.mapScene.removeItem(self)

    def setPositionList(self, startPosition: tuple, positionList: list[tuple]):
        """A new list of points and  line colors for the path.
 
        :param startPosition: The starting point
        :type startPosition: ( deg x, deg y )
        :param positionList: The following points and line colors (HEX color code), color optional
        :type positionList: ((( deg x, deg y ), "#3E69CB" ), ( deg x, deg y ), ... )
        """
        self.__positionList = []
        self.__positionList.append((startPosition, None))
        for item in positionList:
            if isinstance(item[0], tuple):
                self.__positionList.append((item[0], item[1]))
            else:    
                self.__positionList.append((item[0], self.pathColor))
        
        self.draw()

    def addPosition(self, position: tuple, color: str = "#3E69CB", index=-1):
        """Adding a new point to the path list.
 
        :param position:
        :type position: ( deg x, deg y )
        :param color: optional, default = "#3E69CB"
        :type color: HEX color code
        :param index: optional, default = -1
        :type index: The index of the point in the path
        """
        if index == -1:
            self.__positionList.append(position, color)
        else:
            self.__positionList.insert(index, (position, color))
        self.draw()

    def removePosition(self, position: tuple):
        """Remove a point to the path list.
 
        :param position:
        :type position: ( deg x, deg y )
        """
        self.__positionList.remove(position)
        self.draw()

    def setVisiblePath(self, visible: bool):
        """Path visibility. """
        self.pathVisible = visible
        self.draw()
    
    # Working methods
    def __getCanvasPos(self, position, widgetTileWidth, widgetTileHeight):
        tilePosition = decimal_to_osm(*position, round(self.mapView.zoom))

        canvas_pos_x = ((tilePosition[0] - self.mapView.upperLeftTilePos[0]) / widgetTileWidth) * self.mapView._width
        canvas_pos_y = ((tilePosition[1] - self.mapView.upperLeftTilePos[1]) / widgetTileHeight) * self.mapView._height

        return canvas_pos_x, canvas_pos_y
    
    def draw(self, move=False):
        if self.pathVisible == True:
            self.setVisible(True)
            
            new_line_length = self.__lastPositionListLength != len(self.__positionList)
            self.__lastPositionListLength = len(self.__positionList)

            widgetTileWidth = self.mapView.lowerRightTilePos[0] - self.mapView.upperLeftTilePos[0]
            widgetTileHeight = self.mapView.lowerRightTilePos[1] - self.mapView.upperLeftTilePos[1]

            if move is True and self.__lastUpperLeftTilePos is not None and new_line_length is False:
                x_move = ((self.__lastUpperLeftTilePos[0] - self.mapView.upperLeftTilePos[0]) / widgetTileWidth) * self.mapView._width
                y_move = ((self.__lastUpperLeftTilePos[1] - self.mapView.upperLeftTilePos[1]) / widgetTileHeight) * self.mapView._height

                for i in range(0, len(self.__positionList)* 2, 2):
                    self.__canvasLinePositions[i] += x_move
                    self.__canvasLinePositions[i + 1] += y_move
            else:
                self.__canvasLinePositions = []
                for position in self.__positionList:
                    canvas_position = self.__getCanvasPos(position[0], widgetTileWidth, widgetTileHeight)
                    self.__canvasLinePositions.append(canvas_position[0])
                    self.__canvasLinePositions.append(canvas_position[1])

            segments = int(len(self.__canvasLinePositions) / 2 - 1)
            if self.__segments != segments:
                index = 0
                for i in range(0, segments - self.__segments):
                    self.__segments += 1
                    lineItem = QGraphicsLineItem(self.__canvasLinePositions[index], self.__canvasLinePositions[index + 1],
                                                 self.__canvasLinePositions[index + 2], self.__canvasLinePositions[index + 3], self)
                    index +=2
                    self.__canvasLine.append((lineItem, QColor(self.__positionList[int(index/2)][1])))
                    line_pen = QPen(self.__canvasLine[-1][1])
                    line_pen.setWidth(self.widthLine)
                    lineItem.setPen(line_pen)
            else:
                index = 0
                for item in self.__canvasLine:
                    item[0].setLine(self.__canvasLinePositions[index], self.__canvasLinePositions[index + 1],
                                 self.__canvasLinePositions[index + 2], self.__canvasLinePositions[index + 3])
                    line_pen = QPen(item[1])
                    line_pen.setWidth(self.widthLine)
                    item[0].setPen(line_pen)
                    index+=2

            self.__lastUpperLeftTilePos = self.mapView.upperLeftTilePos
        else:
            self.setVisible(False)

    # Events
    def hoverEnterEvent(self, event):
        if self.command != None and self.pathVisible == True:
            QApplication.setOverrideCursor(QCursor(Qt.PointingHandCursor))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.command != None and self.pathVisible == True:
            QApplication.restoreOverrideCursor()
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        if self.command != None:
            self.command(self)
        super().mousePressEvent(event)
    