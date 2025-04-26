from PyQt5.QtWidgets import QApplication, QGraphicsPixmapItem, QGraphicsTextItem
from PyQt5.QtGui import QCursor, QFont, QPixmap, QColor, QImage
from PyQt5.QtCore import Qt

import os
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .mapView import PyQtMapView

from .utility_functions import decimal_to_osm, osm_to_decimal


class MapPositionMarker(QGraphicsPixmapItem):
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
            
            # if self.image is not None and self.imageZoomVisibility[0] <= self.mapView.zoom <= self.imageZoomVisibility[1]\
            #         and not self.imageVisible:
            #     if self.canvasImage is None:
            #         self.canvasImage = self.mapView.canvas.create_image(canvasPosX, canvasPosY + (self.textOffsetY - 30),
            #                                                                 anchor=tkinter.S,
            #                                                                 image=self.image,
            #                                                                 tag=("marker", "marker_image"))
            #     else:
            #         self.mapView.canvas.coords(self.canvasImage, canvasPosX, canvasPosY + (self.textOffsetY - 30))
            # else:
            #     if self.canvasImage is not None:
            #         self.mapView.canvas.delete(self.canvasImage)
            #         self.canvasImage = None
        else:
            self.setVisible(False)


