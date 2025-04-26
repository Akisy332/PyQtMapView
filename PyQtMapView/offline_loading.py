import os
import time
import sqlite3
import threading
import requests
import sys
import math
from PIL import Image, UnidentifiedImageError

from PyQt5.QtCore import QThread, pyqtSignal, QObject


from .utility_functions import decimal_to_osm, osm_to_decimal


class OfflineLoader (QObject):
    signalDownloadCountTile = pyqtSignal(int)
    signalDownloadCount = pyqtSignal(int)
    signalZoom = pyqtSignal(int)
    
    def __init__(self, path=None, tile_server=None, name_server = None, max_zoom=19, storage_mode: int = 0, selection_mode: int = 0, console_output: bool = True):
        super().__init__()
        if tile_server is None:
            self.tile_server = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
            self.name_server = "OpenStreetMap"
        else:
            self.tile_server = tile_server
            self.name_server = name_server
        
        # 0 - DataBase, 1 - Files
        if storage_mode > 1:
            self.storage_mode = 0
        else:
            self.storage_mode = storage_mode
            
        if path is None:
            if self.storage_mode == 0:
                self.db_path = os.path.join(os.path.abspath(os.getcwd()), f"{self.name_server}.db")
            else:
                self.db_path = os.path.join(os.path.abspath(os.getcwd()), f"{self.name_server}")
        else:
            if self.storage_mode == 0:
                self.db_path = os.path.join(path, f"{self.name_server}.db")
            else: 
                self.db_path = os.path.join(path, f"{self.name_server}")
        
        # 0 - Rectangles, 1 - Circle
        if selection_mode > 1:
            self.selection_mode = 0
        else:
            self.selection_mode = selection_mode
            
        self.max_zoom = max_zoom
        self.console_output = console_output
        
        self.task_queue = []
        self.result_queue = []
        self.thread_pool = []
        self.lock = threading.Lock()
        self.number_of_threads = 50
        
        self.running = True
        
    def save_offline_tiles_thread(self):
        if self.storage_mode == 0: 
            db_connection = sqlite3.connect(self.db_path, timeout=10)
            db_cursor = db_connection.cursor()

        while True:
            self.lock.acquire()
            if len(self.task_queue) > 0:
                task = self.task_queue.pop()
                self.lock.release()
                zoom, x, y = task[0], task[1], task[2]
                flag = 1
                if self.storage_mode == 0: 
                    check_existence_cmd = f"""SELECT t.zoom, t.x, t.y FROM tiles t WHERE t.zoom=? AND t.x=? AND t.y=? AND server=?;"""
                    try:
                        db_cursor.execute(check_existence_cmd, (zoom, x, y, self.tile_server))
                    except sqlite3.OperationalError:
                        self.lock.acquire()
                        self.task_queue.append(task)
                        self.lock.release()
                        continue
                    result = db_cursor.fetchall()
                    flag = len(result)
                elif self.storage_mode == 1:
                    tile_path = os.path.join(self.db_path, self.name_server, f"{zoom}", f"{x}", f"{y}.png")
                    if(not os.path.exists(tile_path)):
                       flag = 0
                    
                if flag == 0:

                    try:
                        url = self.tile_server.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
                        image_data = requests.get(url, stream=True, headers={"User-Agent": "PyQtMapView"}).content

                        self.lock.acquire()
                        self.result_queue.append((zoom, x, y, self.tile_server, image_data))
                        self.lock.release()

                    except sqlite3.OperationalError:
                        self.lock.acquire()
                        self.task_queue.append(task)  # re-append task to task_queue
                        self.lock.release()

                    except UnidentifiedImageError:
                        self.lock.acquire()
                        self.result_queue.append((zoom, x, y, self.tile_server, None))
                        self.lock.release()

                    except Exception as err:
                        sys.stderr.write(str(err) + "\n")
                        self.lock.acquire()
                        self.task_queue.append(task)
                        self.lock.release()
                else:
                    self.lock.acquire()
                    self.result_queue.append((zoom, x, y, self.tile_server, None))
                    self.lock.release()
            else:
                self.lock.release()

            time.sleep(0.01)
    
    def load_task_queue(self, position_a, position_b = None, zoom: int = 0):
        
        self.lock.acquire()
        # Circle
        if self.selection_mode == 1:
            center_circle = position_a
            lat_offset = self.radius / 111.0
            lon_offset = self.radius / (111.0 * math.cos(math.radians(center_circle[0])))
            # Углы квадрата
            upper_left = (center_circle[0] + lat_offset, center_circle[1] - lon_offset)
            lower_right = (center_circle[0] - lat_offset, center_circle[1] + lon_offset)
        
            center = decimal_to_osm(*center_circle, zoom)
            upperLeftTilePos = decimal_to_osm(*upper_left, zoom)
            lowerRightTilePos = decimal_to_osm(*lower_right, zoom)
            # Проходим по всем точкам в квадрате, ограниченном кругом
            for x in range(math.floor(upperLeftTilePos[0]), math.ceil(lowerRightTilePos[0]) + 1):
                for y in range(math.floor(upperLeftTilePos[1]), math.ceil(lowerRightTilePos[1]) + 1):
                    # Проверяем, находится ли точка (x, y) внутри круга
                    if ((x - round(center[0])) ** 2 + 
                        (y - round(center[1])) ** 2 <= 
                        round(upperLeftTilePos[0] - center[0]) ** 2 and x >= 0 and y >= 0):
                        
                        element = (zoom, x, y)
                        if element not in self.task_queue:
                            self.task_queue.append(element)
        # Rectangles
        else:
            upperLeftTilePos = decimal_to_osm(*position_a, zoom)
            lowerRightTilePos = decimal_to_osm(*position_b, zoom)
            for x in range(math.floor(upperLeftTilePos[0]), math.ceil(lowerRightTilePos[0]) + 1):
                for y in range(math.floor(upperLeftTilePos[1]), math.ceil(lowerRightTilePos[1]) + 1):
                    self.task_queue.append((zoom, x, y))
        self.number_of_tasks = len(self.task_queue)
        self.lock.release()
        
        if self.console_output == True:
            print(f"[save_offline_tiles] zoom: {zoom:<2}  tiles: {self.number_of_tasks:<8}  storage: {math.ceil(self.number_of_tasks * 8 / 1024):>6} MB", end="")
            print(f"  progress: ", end="")
        
        self.signalZoom.emit(zoom)
        self.signalDownloadCount.emit(self.number_of_tasks)
    
    def save_offline_tiles(self, position_a, position_b = None, zoom_a = 0, zoom_b = 12, radius: int = None):
        
        if self.selection_mode == 0:
            if position_b is None:
                sys.stderr.write("position_b is None" + "\n")
                return
        else:
            if radius <= 0:
                radius = 100 # km
            self.radius = radius
            
        if self.storage_mode == 0:
            # connect to database
            db_connection = sqlite3.connect(self.db_path)
            db_cursor = db_connection.cursor()

            # create tables if it not exists
            create_server_table = """CREATE TABLE IF NOT EXISTS server (
                                            url VARCHAR(300) PRIMARY KEY NOT NULL,
                                            max_zoom INTEGER NOT NULL);"""

            create_tiles_table = """CREATE TABLE IF NOT EXISTS tiles (
                                            zoom INTEGER NOT NULL,
                                            x INTEGER NOT NULL,
                                            y INTEGER NOT NULL,
                                            server VARCHAR(300) NOT NULL,
                                            tile_image BLOB NOT NULL,
                                            CONSTRAINT fk_server FOREIGN KEY (server) REFERENCES server (url),
                                            CONSTRAINT pk_tiles PRIMARY KEY (zoom, x, y, server));"""

            db_cursor.execute(create_server_table)
            db_cursor.execute(create_tiles_table)
            db_connection.commit()

            # insert tile_server if not in database
            db_cursor.execute(f"SELECT * FROM server s WHERE s.url='{self.tile_server}';")
            if len(db_cursor.fetchall()) == 0:
                db_cursor.execute(f"INSERT INTO server (url, max_zoom) VALUES (?, ?);", (self.tile_server, self.max_zoom))
                db_connection.commit()

        # create threads
        for i in range(self.number_of_threads):
            thread = threading.Thread(daemon=True, target=self.save_offline_tiles_thread, args=())
            self.thread_pool.append(thread)

        # start threads
        for thread in self.thread_pool:
            thread.start()
        self.running = True
        
        # loop through all zoom levels
        for zoom in range(round(zoom_a), round(zoom_b + 1)):
            self.load_task_queue(position_a = position_a, position_b = position_b,zoom = zoom)
            
            result_counter = 0
            loading_bar_length = 0
            while result_counter < self.number_of_tasks:
                if self.running is False:
                    zoom = zoom - 1
                    break
                self.lock.acquire()
                if len(self.result_queue) > 0:
                    loading_result = self.result_queue.pop()
                    self.lock.release()
                    result_counter += 1

                    if loading_result[-1] is not None:
                        if self.storage_mode == 0:
                            insert_tile_cmd = """INSERT INTO tiles (zoom, x, y, server, tile_image) VALUES (?, ?, ?, ?, ?);"""
                            db_cursor.execute(insert_tile_cmd, loading_result)
                            db_connection.commit()
                        else:

                            tile_path = os.path.join(self.db_path, self.name_server, f"{loading_result[0]}", f"{loading_result[1]}", f"{loading_result[2]}.png")
                            os.makedirs(os.path.dirname(tile_path), exist_ok=True)
                            with open(tile_path, 'wb') as tile_file:
                                tile_file.write(loading_result[4])
                else:
                    self.lock.release()

                # update loading bar to current progress (percent)
                self.signalDownloadCountTile.emit(result_counter)
                
                if self.console_output is True:
                    percent = result_counter / self.number_of_tasks
                    length = round(percent * 30)
                    while length > loading_bar_length:
                        print("█", end="")
                        loading_bar_length += 1
                    
            if self.running is False: 
                break
            if self.console_output is True:
                print(f" {result_counter:>8} tiles loaded")
        if self.console_output is True:
            print("", end="\n\n")
        if self.storage_mode == 0:
            db_connection.close()
        return

    def stop_download(self):
        self.running = False