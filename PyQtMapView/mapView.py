import sys
from PyQt5.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItemGroup, QPushButton
from PyQt5.QtGui import QPixmap, QColor, QImage, QPainter, QIcon
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal, QSize, QPoint, pyqtSlot
from PyQt5.QtWidgets import QMenu, QMessageBox
from PyQt5.QtCore import qSetMessagePattern

import os
import requests
import math
import threading
import time
import io
import sqlite3
import geocoder
from typing import Callable, List, Dict, Union, Tuple
from functools import partial

from .element import Tile, Marker, Buttons, Path
from .utility_functions import decimal_to_osm, osm_to_decimal


class PyQtMapView(QGraphicsView):
    def __init__(self, *args,
                 width: int = 300,
                 height: int = 200,
                 dataPath: str | None = None,
                 useDatabaseOnly: bool = False,
                 buttons: bool = True,
                 **kwargs):
        super().__init__(*args, **kwargs)
        # qSetMessagePattern('%{appname} %{file} %{function} %{line} %{threadid}  %{backtrace depth=10 separator=\"\n\"}')
        # Создаем сцену
        self.mapScene = QGraphicsScene(self)
        self.setGeometry(0, 0, width, height)
        self.setScene(self.mapScene)
        self.setSceneRect(0, 0, width, height)
        self.setCursor(Qt.ArrowCursor)
        
        # Настройка представления
        self.setRenderHint(QPainter.Antialiasing)
        
        # Убираем скроллбары
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Создаем группу для тайлов
        self.tile_group = QGraphicsItemGroup() 
        self.mapScene.addItem(self.tile_group) 
        
        # map layers
        self.mapLayers: list[dict] = []
        self.mapLayers.append({'nameMap': 'Open Street Map',
                                        'tileServer': 'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                                        'tileSize': 256,
                                        'nameDir': 'OpenStreetMap',
                                        'maxZoom': 19})
        self.mapLayers.append({'nameMap': 'Google satellite',
                                        'tileServer': 'https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga',
                                        'tileSize': 256,
                                        'nameDir': 'GoogleSattelite' ,
                                        'maxZoom': 22})
        self.mapLayers.append({'nameMap': 'Google normal',
                                        'tileServer': 'https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga',
                                        'tileSize': 256,
                                        'nameDir': 'GoogleNormal' ,
                                        'maxZoom': 22})
        
        self.currentLayers: int = 0
        
        self.running = True
        self.init = True
        
        self._width = width
        self._height = height

        # bind events for mouse button pressed, mouse movement, and scrolling
        self.last_mouse_down_position: Union[tuple, None] = None
        self.last_mouse_down_time: Union[float, None] = None
        self.mouse_click_position: Union[tuple, None] = None
        self.map_click_callback: Union[Callable, None] = None  # callback function for left click on map
        self.is_dragging = False
        
        # movement fading
        self.move_velocity: Tuple[float, float] = (0, 0)
        self.last_move_time: Union[float, None] = None
        self.fadingTimer = QTimer()                         
        self.fadingTimer.setInterval(1) 
        self.fadingTimer.timeout.connect(self.__fadingMove)    

        # canvas objects
        self.canvas_tile_array: List[List[Tile]] = []
        self.elementsList: List[Marker] = []
         
        # describes the tile layout
        self.zoom: float = 0
        self.upperLeftTilePos: Tuple[float, float] = (0, 0)  # in OSM coords
        self.lowerRightTilePos: Tuple[float, float] = (0, 0)
        self.last_zoom: float = self.zoom
        
        self.setTileServer('Open Street Map', dataPath=dataPath)
        
        # set initial position
        self.setZoom(17)
        self.setPosition((56.45112740752376, 84.96449640447315))  # Brandenburger Tor, Berlin

        # right click menu
        self.right_click_menu_commands: List[dict] = []  # list of dictionaries with "label": str, "command": Callable, "pass_coords": bool

        if buttons is True:
            self.addElement(Buttons())
        
        self.init = False
        
    
    def destroy(self):
        self.running = False
        super().destroy()

    def add_right_click_menu_command(self, label: str, command: Callable, pass_coords: bool = False) -> None:
        self.right_click_menu_commands.append({"label": label, "command": command, "pass_coords": pass_coords})

    def add_left_click_map_command(self, callback_function):
        self.map_click_callback = callback_function
    
    def convert_canvas_coords_to_decimal_coords(self, canvas_x: int, canvas_y: int) -> tuple:
        relative_mouse_x = canvas_x / self._width
        relative_mouse_y = canvas_y / self._height

        tile_mouse_x = self.upperLeftTilePos[0] + (self.lowerRightTilePos[0] - self.upperLeftTilePos[0]) * relative_mouse_x
        tile_mouse_y = self.upperLeftTilePos[1] + (self.lowerRightTilePos[1] - self.upperLeftTilePos[1]) * relative_mouse_y

        coordinate_mouse_pos = osm_to_decimal(tile_mouse_x, tile_mouse_y, round(self.zoom))
        return coordinate_mouse_pos
    
    # debug
    def fit_bounding_box(self, position_top_left: Tuple[float, float], position_bottom_right: Tuple[float, float]):
        """ Fit the map to contain a bounding box with the maximum zoom level possible. """

        # check positions
        if not (position_top_left[0] > position_bottom_right[0] and position_top_left[1] < position_bottom_right[1]):
            raise ValueError("incorrect bounding box positions, <must be top_left_position> <bottom_right_position>")

        last_fitting_zoom_level = self.minZoom
        middle_position_lat, middle_position_long = (position_bottom_right[0] + position_top_left[0]) / 2, (position_bottom_right[1] + position_top_left[1]) / 2

        # loop through zoom levels beginning at minimum zoom
        for zoom in range(self.minZoom, self.maxZoom + 1):
            # calculate tile positions for bounding box
            middle_tile_position = decimal_to_osm(middle_position_lat, middle_position_long, zoom)
            top_left_tile_position = decimal_to_osm(*position_top_left, zoom)
            bottom_right_tile_position = decimal_to_osm(*position_bottom_right, zoom)

            # calculate tile positions for map corners
            calc_top_left_tile_position = (middle_tile_position[0] - ((self.width / 2) / self.tileSize),
                                           middle_tile_position[1] - ((self.height / 2) / self.tileSize))
            calc_bottom_right_tile_position = (middle_tile_position[0] + ((self.width / 2) / self.tileSize),
                                               middle_tile_position[1] + ((self.height / 2) / self.tileSize))

            # check if bounding box fits in map
            if calc_top_left_tile_position[0] < top_left_tile_position[0] and calc_top_left_tile_position[1] < top_left_tile_position[1] \
                    and calc_bottom_right_tile_position[0] > bottom_right_tile_position[0] and calc_bottom_right_tile_position[1] > bottom_right_tile_position[1]:
                # set last_fitting_zoom_level to current zoom becuase bounding box fits in map
                last_fitting_zoom_level = zoom
            else:
                # break because bounding box does not fit in map
                break

        # set zoom to last fitting zoom and position to middle position of bounding box
        self.setZoom(last_fitting_zoom_level)
        self.setPosition((middle_position_lat, middle_position_long))
    
    
    # debug
    def set_address(self, address_string: str, marker: bool = False, text: str = None, **kwargs) -> Marker:
        """ Function uses geocode service of OpenStreetMap (Nominatim).
            https://geocoder.readthedocs.io/providers/OpenStreetMap.html """

        result = geocoder.osm(address_string)

        if result.ok:

            # determine zoom level for result by bounding box
            if hasattr(result, "bbox"):
                zoom_not_possible = True

                for zoom in range(self.minZoom, self.maxZoom + 1):
                    lower_left_corner = decimal_to_osm(*result.bbox['southwest'], zoom)
                    upper_right_corner = decimal_to_osm(*result.bbox['northeast'], zoom)
                    tile_width = upper_right_corner[0] - lower_left_corner[0]

                    if tile_width > math.floor(self.width / self.tileSize):
                        zoom_not_possible = False
                        self.setZoom(zoom)
                        break

                if zoom_not_possible:
                    self.setZoom(self.maxZoom)
            else:
                self.setZoom(10)

            if text is None:
                try:
                    text = result.geojson['features'][0]['properties']['address']
                except:
                    text = address_string

            return self.setPosition(*result.latlng, marker=marker, text=text, **kwargs)
        else:
            return False
    
    
    def addElement(self, element):
        """ Add new element on map """
        element.mapView = self
        if isinstance(element, Buttons):
            self.buttons = element
            element.addButtons()            
        else:
            self.elementsList.append(element)
            self.mapScene.addItem(element)
            element.draw()
    
    def removeElement(self, element):
        None
        
    # debug
    def delete_all_marker(self):
        for i in range(len(self.elementsList) - 1, -1, -1):
            self.elementsList[i].delete()
        self.elementsList = []
    
    # debug
    def clearScene(self):
        for itemA in self.canvas_tile_array:
            for itemB in itemA:
                self.mapScene.removeItem(itemB.pixmap_item)
    
    
    
    def addTileServer(self, nameMap: str, nameDir: str,  tileServer: str, tileSize: int = 256, maxZoom: int = 19):
        """ Adds a new server for tiles """
        layer = {'nameMap': nameMap,
                 'tileServer': tileServer,
                 'tileSize': tileSize,
                 'nameDir': nameDir,
                 'maxZoom': maxZoom}
        self.mapLayers.append(layer)
    
    def removeTileServer(self, nameMap: str) -> bool:
        """ Deletes the tile server, returns True if deleted """
        for i, server in enumerate(self.mapLayers):
            if server.get("nameMap") == nameMap:
                if i == self.currentLayers:
                    if i == len(self.mapLayers)-1:
                        self.setTileServer(self.mapLayers[i-1].get('nameMap'))
                    else:
                        self.setTileServer(self.mapLayers[i].get('nameMap'))
                self.mapLayers.pop(i)
                return True
        return False
    
    def setTileServer(self, tileServer: str, useDatabaseOnly: bool = False, dataPath: str | None = None):
        """ Sets a defined tile server """
        for i, server in enumerate(self.mapLayers):
            if server.get("nameMap") == tileServer:
                self.currentLayers = i
                break
        else:
            self.currentLayers = 0
            
        self.tileServer: str = self.mapLayers[self.currentLayers].get('tileServer')
        self.tileSize: int = self.mapLayers[self.currentLayers].get('tileSize')
        if dataPath is None:
            dataPath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "TileStorage")
        dataPath = os.path.join(dataPath, f"{self.mapLayers[self.currentLayers].get('nameDir')}")
        self.maxZoom = self.mapLayers[self.currentLayers].get('maxZoom')  # should be set according to tile server max zoom
        self.minZoom: int = math.ceil(math.log2(math.ceil(self._width / self.tileSize)))  # min zoom at which map completely fills widget    
        
        if not self.init is True:
            self.tileManager.setDataPath(dataPath, True)
            self.clearScene()
            self.__drawInitialArray()
        else:
            self.tileManager = TileManager(self, useDatabaseOnly, dataPath)
    
    def getTileServer(self) -> str:
        """ Returns the current tile server """
        return self.mapLayers[self.currentLayers].get('nameMap')
    
    def getPosition(self) -> tuple:
        """ Returns current middle position of map widget in decimal coordinates """

        return osm_to_decimal((self.lowerRightTilePos[0] + self.upperLeftTilePos[0]) / 2,
                              (self.lowerRightTilePos[1] + self.upperLeftTilePos[1]) / 2,
                              round(self.zoom))

    def setPosition(self, position: tuple):
        """ Set new middle position of map in decimal coordinates """

        # convert given decimal coordinates to OSM coordinates and set corner positions accordingly
        current_tile_position = decimal_to_osm(position[0], position[1], round(self.zoom))
        
        self.upperLeftTilePos = (current_tile_position[0] - ((self._width / 2) / self.tileSize),
                                    current_tile_position[1] - ((self._height / 2) / self.tileSize))

        self.lowerRightTilePos = (current_tile_position[0] + ((self._width / 2) / self.tileSize),
                                     current_tile_position[1] + ((self._height / 2) / self.tileSize))
        

        self.__checkMapBorderCrossing()
        self.__drawInitialArray()
    
    def setZoom(self, zoom: int, relative_pointer_x: float = 0.5, relative_pointer_y: float = 0.5):
        """ Sets the zoom of the map """
        mouse_tile_pos_x = self.upperLeftTilePos[0] + (self.lowerRightTilePos[0] - self.upperLeftTilePos[0]) * relative_pointer_x
        mouse_tile_pos_y = self.upperLeftTilePos[1] + (self.lowerRightTilePos[1] - self.upperLeftTilePos[1]) * relative_pointer_y
        
        current_deg_mouse_position = osm_to_decimal(mouse_tile_pos_x,
                                                    mouse_tile_pos_y,
                                                    round(self.zoom))
        self.zoom = zoom
        
        if self.zoom > self.maxZoom:
            self.zoom = self.maxZoom
        if self.zoom < self.minZoom:
            self.zoom = self.minZoom
        
        current_tile_mouse_position = decimal_to_osm(*current_deg_mouse_position, round(self.zoom))

        self.upperLeftTilePos = (current_tile_mouse_position[0] - relative_pointer_x * (self._width / self.tileSize),
                                    current_tile_mouse_position[1] - relative_pointer_y * (self._height / self.tileSize))
       
        self.lowerRightTilePos = (current_tile_mouse_position[0] + (1 - relative_pointer_x) * (self._width / self.tileSize),
                                     current_tile_mouse_position[1] + (1 - relative_pointer_y) * (self._height / self.tileSize))
        
        if round(self.zoom) != round(self.last_zoom):
            self.__checkMapBorderCrossing()
            self.__drawZoom()
            self.last_zoom = round(self.zoom)
    
    def getZoom(self) -> int:
        """ Returns the current zoom """
        return round(self.zoom)
        
        
    def __insertRow(self, insert: int, y_name_position: int):

        for x_pos in range(len(self.canvas_tile_array)):
            tile_name_position = self.canvas_tile_array[x_pos][0].tile_name_position[0], y_name_position

            image = self.tileManager.getTileImageFromCache(round(self.zoom), *tile_name_position)
            if image is False:
                tile = Tile(self, self.tileManager.notLoadedTileImage, tile_name_position)
                self.tileManager.imageLoadQueueTasks.append(((round(self.zoom), *tile_name_position), tile))
            else:
                tile = Tile(self, image, tile_name_position)

            tile.draw()

            self.canvas_tile_array[x_pos].insert(insert, tile)   
    
    def __insertColumn(self, insert: int, x_name_position: int):
        canvas_tile_column = []

        for y_pos in range(len(self.canvas_tile_array[0])):
            tile_name_position = x_name_position, self.canvas_tile_array[0][y_pos].tile_name_position[1]

            image = self.tileManager.getTileImageFromCache(round(self.zoom), *tile_name_position)
            if image is False:
                # image is not in image cache, load blank tile and append position to image_load_queue
                tile = Tile(self, self.tileManager.notLoadedTileImage, tile_name_position)
                self.tileManager.imageLoadQueueTasks.append(((round(self.zoom), *tile_name_position), tile))
            else:
                # image is already in cache
                tile = Tile(self, image, tile_name_position)

            tile.draw()

            canvas_tile_column.append(tile)

        self.canvas_tile_array.insert(insert, canvas_tile_column)       
           
    def __drawInitialArray(self):
        self.tileManager.imageLoadQueueTasks = []

        x_tile_range = math.ceil(self.lowerRightTilePos[0]) - math.floor(self.upperLeftTilePos[0])
        y_tile_range = math.ceil(self.lowerRightTilePos[1]) - math.floor(self.upperLeftTilePos[1])

        # upper left tile name position
        upper_left_x = math.floor(self.upperLeftTilePos[0])
        upper_left_y = math.floor(self.upperLeftTilePos[1])

        for x_pos in range(len(self.canvas_tile_array)):
            for y_pos in range(len(self.canvas_tile_array[0])):
                self.canvas_tile_array[x_pos][y_pos].__del__()

        # create tile array with size (x_tile_range x y_tile_range)
        self.canvas_tile_array = []

        for x_pos in range(x_tile_range):
            canvas_tile_column = []

            for y_pos in range(y_tile_range):
                tile_name_position = upper_left_x + x_pos, upper_left_y + y_pos

                image = self.tileManager.getTileImageFromCache(round(self.zoom), *tile_name_position)
                if image is False:
                    # image is not in image cache, load blank tile and append position to image_load_queue
                    tile = Tile(self, self.tileManager.notLoadedTileImage, tile_name_position)
                    self.tileManager.imageLoadQueueTasks.append(((round(self.zoom), *tile_name_position), tile))
                else:
                    # image is already in cache
                    tile = Tile(self, image, tile_name_position)

                canvas_tile_column.append(tile)

            self.canvas_tile_array.append(canvas_tile_column)

        # draw all canvas tiles
        for x_pos in range(len(self.canvas_tile_array)):
            for y_pos in range(len(self.canvas_tile_array[0])):
                self.canvas_tile_array[x_pos][y_pos].draw()
                
        # # draw other objects on canvas
        for element in self.elementsList:
            element.draw()

        # update pre-cache position
        self.tileManager.preCachePosition = (round((self.upperLeftTilePos[0] + self.lowerRightTilePos[0]) / 2),
                                   round((self.upperLeftTilePos[1] + self.lowerRightTilePos[1]) / 2))
        
        self.mapScene.update()
        
    def __drawMove(self, called_after_zoom: bool = False):

        if self.canvas_tile_array:
            # insert or delete rows on top
            top_y_name_position = self.canvas_tile_array[0][0].tile_name_position[1]
            top_y_diff = self.upperLeftTilePos[1] - top_y_name_position
            if top_y_diff <= 0:
                for y_diff in range(1, math.ceil(-top_y_diff) + 1):
                    self.__insertRow(insert=0, y_name_position=top_y_name_position - y_diff)
            elif top_y_diff >= 1:
                for y_diff in range(1, math.ceil(top_y_diff)):
                    for x in range(len(self.canvas_tile_array) - 1, -1, -1):
                        if len(self.canvas_tile_array[x]) > 1:
                            self.canvas_tile_array[x][0].delete()
                            del self.canvas_tile_array[x][0]

            # insert or delete columns on left
            left_x_name_position = self.canvas_tile_array[0][0].tile_name_position[0]
            left_x_diff = self.upperLeftTilePos[0] - left_x_name_position
            if left_x_diff <= 0:
                for x_diff in range(1, math.ceil(-left_x_diff) + 1):
                    self.__insertColumn(insert=0, x_name_position=left_x_name_position - x_diff)
            elif left_x_diff >= 1:
                for x_diff in range(1, math.ceil(left_x_diff)):
                    if len(self.canvas_tile_array) > 1:
                        for y in range(len(self.canvas_tile_array[0]) - 1, -1, -1):
                            self.canvas_tile_array[0][y].delete()
                            del self.canvas_tile_array[0][y]
                        del self.canvas_tile_array[0]

            # insert or delete rows on bottom
            bottom_y_name_position = self.canvas_tile_array[0][-1].tile_name_position[1]
            bottom_y_diff = self.lowerRightTilePos[1] - bottom_y_name_position
            if bottom_y_diff >= 1:
                for y_diff in range(1, math.ceil(bottom_y_diff)):
                    self.__insertRow(insert=len(self.canvas_tile_array[0]), y_name_position=bottom_y_name_position + y_diff)
            elif bottom_y_diff <= 1:
                for y_diff in range(1, math.ceil(-bottom_y_diff) + 1):
                    for x in range(len(self.canvas_tile_array) - 1, -1, -1):
                        if len(self.canvas_tile_array[x]) > 1:
                            self.canvas_tile_array[x][-1].delete()
                            del self.canvas_tile_array[x][-1]

            # insert or delete columns on right
            right_x_name_position = self.canvas_tile_array[-1][0].tile_name_position[0]
            right_x_diff = self.lowerRightTilePos[0] - right_x_name_position

            if right_x_diff >= 1:
                for x_diff in range(1, math.ceil(right_x_diff)):
                    self.__insertColumn(insert=len(self.canvas_tile_array), x_name_position=right_x_name_position + x_diff)
            elif right_x_diff <= 1:
                for x_diff in range(1, math.ceil(-right_x_diff) + 1):
                    if len(self.canvas_tile_array) > 1:
                        for y in range(len(self.canvas_tile_array[-1]) - 1, -1, -1):
                            self.canvas_tile_array[-1][y].delete()
                            del self.canvas_tile_array[-1][y]
                        del self.canvas_tile_array[-1]

            # draw all canvas tiles
            for x_pos in range(len(self.canvas_tile_array)):
                for y_pos in range(len(self.canvas_tile_array[0])):
                    self.canvas_tile_array[x_pos][y_pos].draw()
            
            # draw other objects on canvas
            for element in self.elementsList:
                element.draw()

            # update pre-cache position
            self.tileManager.preCachePosition = (round((self.upperLeftTilePos[0] + self.lowerRightTilePos[0]) / 2),
                                       round((self.upperLeftTilePos[1] + self.lowerRightTilePos[1]) / 2))

            self.mapScene.update()
            
    def __drawZoom(self):
        
        if self.canvas_tile_array:
            # clear tile image loading queue, so that no old images from other zoom levels get displayed
            self.tileManager.imageLoadQueueTasks = []

            # upper left tile name position
            upper_left_x = math.floor(self.upperLeftTilePos[0])
            upper_left_y = math.floor(self.upperLeftTilePos[1])

            for x_pos in range(len(self.canvas_tile_array)):
                for y_pos in range(len(self.canvas_tile_array[0])):

                    tile_name_position = upper_left_x + x_pos, upper_left_y + y_pos

                    image = self.tileManager.getTileImageFromCache(round(self.zoom), *tile_name_position)
                    if image is False:
                        image = self.tileManager.notLoadedTileImage
                        # noinspection PyCompatibility
                        self.tileManager.imageLoadQueueTasks.append(((round(self.zoom), *tile_name_position), self.canvas_tile_array[x_pos][y_pos]))

                    self.canvas_tile_array[x_pos][y_pos].set_image_and_position(image, tile_name_position)

            self.tileManager.preCachePosition = (round((self.upperLeftTilePos[0] + self.lowerRightTilePos[0]) / 2),
                                       round((self.upperLeftTilePos[1] + self.lowerRightTilePos[1]) / 2))
            
            self.mapScene.update()
            self.__drawMove(called_after_zoom=True)

    def __fadingMove(self):
        delta_t = time.time() - self.last_move_time
        self.last_move_time = time.time()

        # only do fading when at least 10 fps possible and fading is possible (no mouse movement at the moment)
        if delta_t < 0.1 and self.fadingTimer.isActive():

            # calculate fading velocity
            mouse_move_x = self.move_velocity[0] * delta_t
            mouse_move_y = self.move_velocity[1] * delta_t

            # lower the fading velocity
            lowering_factor = 2 ** (-9 * delta_t)
            self.move_velocity = (self.move_velocity[0] * lowering_factor, self.move_velocity[1] * lowering_factor)

            # calculate exact tile size of widget
            tile_x_range = self.lowerRightTilePos[0] - self.upperLeftTilePos[0]
            tile_y_range = self.lowerRightTilePos[1] - self.upperLeftTilePos[1]

            # calculate the movement in tile coordinates
            tile_move_x = (mouse_move_x / self._width) * tile_x_range
            tile_move_y = (mouse_move_y / self._height) * tile_y_range

            # calculate new corner tile positions
            lowerRightTilePos = (self.lowerRightTilePos[0] + tile_move_x, self.lowerRightTilePos[1] + tile_move_y)
            upperLeftTilePos = (self.upperLeftTilePos[0] + tile_move_x, self.upperLeftTilePos[1] + tile_move_y)
            
            self.lowerRightTilePos = lowerRightTilePos
            self.upperLeftTilePos = upperLeftTilePos
            
            self.__checkMapBorderCrossing()
            self.__drawMove()

            if abs(self.move_velocity[0]) > 1 or abs(self.move_velocity[1]) > 1:
                if not self.running:
                    self.fadingTimer.stop()
        
    def __checkMapBorderCrossing(self):
        diff_x, diff_y = 0, 0
        if self.upperLeftTilePos[0] < 0:
            diff_x += 0 - self.upperLeftTilePos[0]

        if self.upperLeftTilePos[1] < 0:
            diff_y += 0 - self.upperLeftTilePos[1]
        if self.lowerRightTilePos[0] > 2 ** round(self.zoom):
            diff_x -= self.lowerRightTilePos[0] - (2 ** round(self.zoom))
        if self.lowerRightTilePos[1] > 2 ** round(self.zoom):
            diff_y -= self.lowerRightTilePos[1] - (2 ** round(self.zoom))
            
        
        self.upperLeftTilePos = self.upperLeftTilePos[0] + diff_x, self.upperLeftTilePos[1] + diff_y
        self.lowerRightTilePos = self.lowerRightTilePos[0] + diff_x, self.lowerRightTilePos[1] + diff_y       
            
            
    # events            
    def resizeEvent(self, event):
        # return
        if not self.buttons.buttonLayers is None:
            self.buttons.buttonLayers.setGeometry(self.size().width() - 55, 20, 35, 35)
        # only redraw if dimensions changed (for performance)
        height = event.size().height() 
        width = event.size().width()
        
        if self._width != width or self._height != height:
            self._width = width+2
            self._height = height+2
            self.setSceneRect(0, 0, self._width, self._height)
            self.minZoom = math.ceil(math.log2(math.ceil(self._width / self.tileSize)))
        
            self.setZoom(self.zoom)  # call zoom to set the position vertices right
            self.__drawMove()  # call move to draw new tiles or delete tiles
            
        super().resizeEvent(event)
    
    def wheelEvent(self, event):
        if self.fadingTimer.isActive():
            self.fadingTimer.stop()
        # Получаем относительное положение курсора мыши
        relative_mouse_x = event.pos().x() / self._width
        relative_mouse_y = event.pos().y() / self._height
        new_zoom = self.zoom + event.angleDelta().y() * 0.01
        self.setZoom(new_zoom, relative_pointer_x=relative_mouse_x, relative_pointer_y=relative_mouse_y)
        super().wheelEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.is_dragging:
            # calculate moving difference from last mouse position
            mouse_move_x = self.last_mouse_down_position[0] - event.x()
            mouse_move_y = self.last_mouse_down_position[1] - event.y()

            # set move velocity for movement fading out
            delta_t = time.time() - self.last_mouse_down_time
            if delta_t == 0:
                self.move_velocity = (0, 0)
            else:
                self.move_velocity = (mouse_move_x / delta_t, mouse_move_y / delta_t)

            # save current mouse position for next move event
            self.last_mouse_down_position = (event.x(), event.y())
            self.last_mouse_down_time = time.time()

            # calculate exact tile size of widget
            tile_x_range = self.lowerRightTilePos[0] - self.upperLeftTilePos[0]
            tile_y_range = self.lowerRightTilePos[1] - self.upperLeftTilePos[1]

            # calculate the movement in tile coordinates
            tile_move_x = (mouse_move_x / float(self._width)) * tile_x_range
            tile_move_y = (mouse_move_y / float(self._height)) * tile_y_range

            # calculate new corner tile positions
            self.lowerRightTilePos = (self.lowerRightTilePos[0] + tile_move_x, self.lowerRightTilePos[1] + tile_move_y)
            self.upperLeftTilePos = (self.upperLeftTilePos[0] + tile_move_x, self.upperLeftTilePos[1] + tile_move_y)

            self.__checkMapBorderCrossing()
            self.__drawMove()
        super().mouseMoveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True  # Устанавливаем флаг перетаскивания
            # Начинаем перемещение группы при нажатии на мышь
            self.fadingTimer.stop()
            self.mouse_click_position = (event.x(), event.y())

            # save mouse position where mouse is pressed down for moving
            self.last_mouse_down_position = (event.x(), event.y())
            self.last_mouse_down_time = time.time()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False  # Сбрасываем флаг перетаскивания
            self.last_move_time = time.time()

            # check if mouse moved after mouse click event
            if self.mouse_click_position == (event.x(), event.y()):
                # mouse didn't move
                if self.map_click_callback is not None:
                    # get decimal coords of current mouse position
                    coordinate_mouse_pos = self.convert_canvas_coords_to_decimal_coords(event.x(), event.y())
                    self.map_click_callback(coordinate_mouse_pos)
            else:
                # mouse was moved, start fading animation
                if not self.fadingTimer.isActive():
                    self.fadingTimer.start()
        super().mouseReleaseEvent(event)
        
    def contextMenuEvent(self, event):
        coordinate_mouse_pos = self.convert_canvas_coords_to_decimal_coords(event.x(), event.y())

        def click_coordinates_event():
            try:
                clipboard = QApplication.clipboard()
                clipboard.setText(f"{coordinate_mouse_pos[0]:.7f} {coordinate_mouse_pos[1]:.7f}")
                QMessageBox.information(self, "", "Coordinates copied to clipboard!")

            except Exception as err:
                QMessageBox.information(self, "", f"Error copying to clipboard.\n{err}")

        m = QMenu(self)
        m.addAction(f"{coordinate_mouse_pos[0]:.7f} {coordinate_mouse_pos[1]:.7f}", click_coordinates_event)

        if len(self.right_click_menu_commands) > 0:
            m.addSeparator()

        for command in self.right_click_menu_commands:
            if command["pass_coords"]:
                m.addAction(command["label"], lambda _, coord=coordinate_mouse_pos: command["command"](coord))
            else:
                m.addAction(command["label"], command["command"])

        m.exec_(event.globalPos())  # display menu
        super().contextMenuEvent(event)
    
    
    
class TileManager:
    def __init__(self, gui: "PyQtMapView", useDatabaseOnly: bool, dataPath: str):
        self.gui = gui
        self.useDatabaseOnly = useDatabaseOnly
        self.dataPath = dataPath
        
        self.running = True
        
        # pre caching for smoother movements (load tile images into cache at a certain radius around the preCachePosition)
        self.preCachePosition: Union[Tuple[float, float], None] = None
        self.preCacheThread = threading.Thread(daemon=True, target=self.preCache)
        self.preCacheThread.start()

        self.tileImageCache: Dict[str, QPixmap] = {}
        
        # image loading in background threads
        self.timer = QTimer()                         
        self.timer.setInterval(5) 
        self.imageLoadQueueTasks: List[tuple] = []  # task: ((zoom, x, y), canvas_tile_object)
        self.imageLoadQueueResults: List[tuple] = []  # result: ((zoom, x, y), canvas_tile_object, photo_image)
        self.timer.timeout.connect(self.updateTileImages)    
        self.imageLoadThreadPool: List[threading.Thread] = []
        self.timer.start()
        
        # add background threads which load tile images from self.imageLoadQueueTasks
        for i in range(25):
            imageLoadThread = threading.Thread(daemon=True, target=self.loadImagesBackground)
            imageLoadThread.start()
            self.imageLoadThreadPool.append(imageLoadThread)
            
        self.setDataPath(dataPath, True)
        
    def createImage(self, color):
        image = QImage(self.gui.tileSize, self.gui.tileSize, QImage.Format_RGB32)
        image.fill(QColor(*color))
        return QPixmap.fromImage(image)
    
    def setDataPath(self, dataPath: str, dataBase: bool):
        self.dataPath = self.dataPath + ".db" if dataBase else dataPath
        self.imageLoadQueueResults = []
        self.imageLoadQueueTasks = []
        self.tileImageCache: Dict[str, QPixmap] = {}
        self.emptyTileImage = self.createImage((190, 190, 190)) # used for zooming and moving
        self.notLoadedTileImage = self.createImage((250, 250, 250)) # only used when image not found on tile server 

    def preCache(self):
        """ single threaded pre-chache tile images in area of self.preCachePosition """
        lastPreCachePosition = None
        radius = 1
        zoom = round(self.gui.zoom)

        if self.dataPath is not None and os.path.exists(self.dataPath):
            
            dbConnection = sqlite3.connect(self.dataPath)
            
            dbCursor = dbConnection.cursor()
        else:
            dbCursor = None

        while self.running:
            if lastPreCachePosition != self.preCachePosition:
                lastPreCachePosition = self.preCachePosition
                zoom = round(self.gui.zoom)
                radius = 1

            if lastPreCachePosition is not None and radius <= 8:

                # pre cache top and bottom row
                for x in range(self.preCachePosition[0] - radius, self.preCachePosition[0] + radius + 1):
                    if f"{zoom}{x}{self.preCachePosition[1] + radius}" not in self.tileImageCache:
                        self.requestImage(zoom, x, self.preCachePosition[1] + radius, dbCursor==dbCursor)
                    if f"{zoom}{x}{self.preCachePosition[1] - radius}" not in self.tileImageCache:
                        self.requestImage(zoom, x, self.preCachePosition[1] - radius, dbCursor=dbCursor)

                # pre cache left and right column
                for y in range(self.preCachePosition[1] - radius, self.preCachePosition[1] + radius + 1):
                    if f"{zoom}{self.preCachePosition[0] + radius}{y}" not in self.tileImageCache:
                        self.requestImage(zoom, self.preCachePosition[0] + radius, y, dbCursor=dbCursor)
                    if f"{zoom}{self.preCachePosition[0] - radius}{y}" not in self.tileImageCache:
                        self.requestImage(zoom, self.preCachePosition[0] - radius, y, dbCursor=dbCursor)

                # raise the radius
                radius += 1
                
            else:
                time.sleep(0.1)

            # 10_000 images = 80 MB RAM-usage
            if len(self.tileImageCache) > 10_000:  # delete random tiles if cache is too large
                # create list with keys to delete
                keys_to_delete = []
                for key in self.tileImageCache.keys():
                    if len(self.tileImageCache) - len(keys_to_delete) > 10_000:
                        keys_to_delete.append(key)

                # delete keys in list so that len(self.tileImageCache) == 10_000
                for key in keys_to_delete:
                    del self.tileImageCache[key]

    def requestImage(self, zoom: int, x: int, y: int, dbCursor=None) -> QPixmap:
        # Если база данных доступна, сначала проверяем, есть ли тайл в базе данных
        if dbCursor is not None:
            try:
                dbCursor.execute("SELECT t.tile_image FROM tiles t WHERE t.zoom=? AND t.x=? AND t.y=? AND t.server=?;",
                                  (zoom, x, y, self.gui.tileServer))
                result = dbCursor.fetchone()

                if result is not None:
                    # Загружаем изображение из базы данных
                    imageData = result[0]
                    imageQt = QPixmap()
                    imageQt.loadFromData(imageData)
                    self.tileImageCache[f"{zoom}{x}{y}"] = imageQt
                    return imageQt
                elif self.useDatabaseOnly:
                    return self.emptyTileImage
                else:
                    pass

            except sqlite3.OperationalError:
                if self.useDatabaseOnly:
                    return self.emptyTileImage
                else:
                    pass

            except Exception:
                return self.emptyTileImage

        # Попробуем получить тайл с сервера
        try:
            url = self.gui.tileServer.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
            response = requests.get(url, stream=True, headers={"User-Agent": "PyQtMapView"})
            response.raise_for_status()  # Проверка на успешный ответ

            imageData = response.content
            imageQt = QPixmap()
            if not imageQt.loadFromData(imageData):
                return self.emptyTileImage  # Если не удалось загрузить изображение

            self.tileImageCache[f"{zoom}{x}{y}"] = imageQt
            return imageQt

        except requests.exceptions.ConnectionError:
            return self.emptyTileImage

        except Exception:
            return self.emptyTileImage
    
    def getTileImageFromCache(self, zoom: int, x: int, y: int):
        if f"{zoom}{x}{y}" not in self.tileImageCache:
            return False
        else:
            return self.tileImageCache[f"{zoom}{x}{y}"]
    
    def loadImagesBackground(self):
        if self.dataPath is not None and os.path.exists(self.dataPath):
            dbConnection = sqlite3.connect(self.dataPath)
            dbCursor = dbConnection.cursor()
        else:
            dbCursor = None

        while self.running:
            if len(self.imageLoadQueueTasks) > 0:
                # task queue structure: [((zoom, x, y), corresponding canvas tile object), ... ]
                task = self.imageLoadQueueTasks.pop()

                zoom = task[0][0]
                x, y = task[0][1], task[0][2]
                tile = task[1]

                image = self.getTileImageFromCache(zoom, x, y)
                if image is False:
                    image = self.requestImage(zoom, x, y, dbCursor=dbCursor)
                    if image is None:
                        self.imageLoadQueueTasks.append(task)
                        continue

                # result queue structure: [((zoom, x, y), corresponding canvas tile object, tile image), ... ]
                self.imageLoadQueueResults.append(((zoom, x, y), tile, image))

            else:
                time.sleep(0.01)        
    
    def updateTileImages(self):
        while len(self.imageLoadQueueResults) > 0 and self.running:
            # result queue structure: [((zoom, x, y), corresponding canvas tile object, tile image), ... ]
            result = self.imageLoadQueueResults.pop(0)

            zoom, x, y = result[0][0], result[0][1], result[0][2]
            tile = result[1]
            image = result[2]

            # check if zoom level of result is still up to date, otherwise don't update image
            if zoom == round(self.gui.zoom):
                tile.setImage(image)
