import sys
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .mapView import PyQtMapView

from .utility_functions import decimal_to_osm, osm_to_decimal


class CanvasPolygon:
    def __init__(self,
                 mapView: "PyQtMapView",
                 position_list: list,
                 outline_color: str = "#3e97cb",
                 fill_color: str = "gray95",
                 border_width: int = 5,
                 command: Callable = None,
                 name: str = None,
                 data: any = None):

        self.mapView = mapView
        self.position_list = position_list  # list with decimal positions
        self.canvas_polygon_positions = []  # list with canvas coordinates positions
        self.canvas_polygon = None
        self.deleted = False

        self.name = name
        self.data = data
        self.outline_color = outline_color
        self.fill_color = fill_color  # can also be None for transparent fill
        self.border_width = border_width
        self.command = command

        self.last_upperLeftTilePos = None
        self.last_position_list_length = len(self.position_list)

    def delete(self):
        self.mapView.canvas.delete(self.canvas_polygon)

        if self in self.mapView.canvas_polygon_list:
            self.mapView.canvas_polygon_list.remove(self)

        self.canvas_polygon = None
        self.deleted = True

    def add_position(self, deg_x, deg_y, index=-1):
        if index == -1:
            self.position_list.append((deg_x, deg_y))
        else:
            self.position_list.insert(index, (deg_x, deg_y))
        self.draw()

    def remove_position(self, deg_x, deg_y):
        self.position_list.remove((deg_x, deg_y))
        self.draw()

    def mouse_enter(self, event=None):
        if sys.platform == "darwin":
            self.mapView.canvas.config(cursor="pointinghand")
        elif sys.platform.startswith("win"):
            self.mapView.canvas.config(cursor="hand2")
        else:
            self.mapView.canvas.config(cursor="hand2")  # not tested what it looks like on Linux!

    def mouse_leave(self, event=None):
        self.mapView.canvas.config(cursor="arrow")

    def click(self, event=None):
        if self.command is not None:
            self.command(self)

    def get_canvas_pos(self, position, widget_tile_width, widget_tile_height):
        tile_position = decimal_to_osm(*position, round(self.mapView.zoom))

        canvas_pos_x = ((tile_position[0] - self.mapView.upperLeftTilePos[0]) / widget_tile_width) * self.mapView._width
        canvas_pos_y = ((tile_position[1] - self.mapView.upperLeftTilePos[1]) / widget_tile_height) * self.mapView._height

        return canvas_pos_x, canvas_pos_y

    def draw(self, move=False):
        # check if number of positions in position_list has changed
        new_line_length = self.last_position_list_length != len(self.position_list)
        self.last_position_list_length = len(self.position_list)

        # get current tile size of map widget
        widget_tile_width = self.mapView.lowerRightTilePos[0] - self.mapView.upperLeftTilePos[0]
        widget_tile_height = self.mapView.lowerRightTilePos[1] - self.mapView.upperLeftTilePos[1]

        # if only moving happened and len(self.position_list) did not change, shift current positions, else calculate new position_list
        if move is True and self.last_upperLeftTilePos is not None and new_line_length is False:
            x_move = ((self.last_upperLeftTilePos[0] - self.mapView.upperLeftTilePos[0]) / widget_tile_width) * self.mapView._width
            y_move = ((self.last_upperLeftTilePos[1] - self.mapView.upperLeftTilePos[1]) / widget_tile_height) * self.mapView._height

            for i in range(0, len(self.position_list) * 2, 2):
                self.canvas_polygon_positions[i] += x_move
                self.canvas_polygon_positions[i + 1] += y_move
        else:
            self.canvas_polygon_positions = []
            for position in self.position_list:
                canvas_position = self.get_canvas_pos(position, widget_tile_width, widget_tile_height)
                self.canvas_polygon_positions.append(canvas_position[0])
                self.canvas_polygon_positions.append(canvas_position[1])

        if not self.deleted:
            if self.canvas_polygon is None:
                self.mapView.canvas.delete(self.canvas_polygon)
                self.canvas_polygon = self.mapView.canvas.create_polygon(self.canvas_polygon_positions,
                                                                            width=self.border_width,
                                                                            outline=self.outline_color,
                                                                            joinstyle=tkinter.ROUND,
                                                                            stipple="gray25",
                                                                            tag="polygon")
                if self.fill_color is None:
                    self.mapView.canvas.itemconfig(self.canvas_polygon, fill="")
                else:
                    self.mapView.canvas.itemconfig(self.canvas_polygon, fill=self.fill_color)
                    
            else:
                self.mapView.canvas.coords(self.canvas_polygon, self.canvas_polygon_positions)
        else:
            self.mapView.canvas.delete(self.canvas_polygon)
            self.canvas_polygon = None

        self.mapView.manage_z_order()
        self.last_upperLeftTilePos = self.mapView.upperLeftTilePos
