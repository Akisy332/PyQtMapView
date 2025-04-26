from PyQt5.QtWidgets import QApplication, QGraphicsLineItem
from PyQt5.QtGui import QCursor, QColor, QPen
from PyQt5.QtCore import Qt

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .mapView import PyQtMapView

from .utility_functions import decimal_to_osm

class MapPath(QGraphicsLineItem):
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
        
        self.mapView.mapPathList.append(self)
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
        self.mapView.mapPathList.remove(self)
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
    