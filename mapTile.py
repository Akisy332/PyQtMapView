from PyQt5.QtWidgets import QGraphicsPixmapItem

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .mapView import PyQtMapView


class CanvasTile:
    def __init__(self, mapView: "PyQtMapView", image, tile_name_position):
        self.mapView = mapView
        self.image = image
        self.tile_name_position = tile_name_position
        
        self.pixmap_item = None

        self.canvas_object = None
        self.widget_tile_width = 0
        self.widget_tile_height = 0

    def __del__(self):
        # if CanvasTile object gets garbage collected or deleted, delete image from canvas
        self.delete()

    def set_image_and_position(self, image, tile_name_position):
        self.image = image
        self.tile_name_position = tile_name_position
        self.draw(image_update=True)

    def set_image(self, image):
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
            if not (self.image == self.mapView.not_loaded_tile_image or self.image == self.mapView.empty_tile_image):
                self.canvas_object = self.mapView.tile_group
                self.pixmap_item = QGraphicsPixmapItem(self.image)
                self.pixmap_item.setPos(canvas_pos_x, canvas_pos_y)
                self.canvas_object.addToGroup(self.pixmap_item)  
        else:
            self.pixmap_item.setPos(canvas_pos_x, canvas_pos_y)

            if image_update:
                if not (self.image == self.mapView.not_loaded_tile_image or self.image == self.mapView.empty_tile_image):
                    self.pixmap_item.setPixmap(self.image)
                else:
                    if not self.pixmap_item == None:
                        self.mapView.mapScene.removeItem(self.pixmap_item)
                    self.canvas_object = None
