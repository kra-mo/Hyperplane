# item.py
#
# Copyright 2023 kramo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""An item represeting a file to be set up thorugh a `GtkSignalListItemFactory`."""
from pathlib import Path
from typing import Any, Optional

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from hyperplane import shared
from hyperplane.utils.get_color_for_content_type import get_color_for_content_type
from hyperplane.utils.thumbnail import generate_thumbnail


@Gtk.Template(resource_path=shared.PREFIX + "/gtk/item.ui")
class HypItem(Adw.Bin):
    """An item represeting a file to be set up thorugh a `GtkSignalListItemFactory`."""

    __gtype_name__ = "HypItem"

    clamp: Adw.Clamp = Gtk.Template.Child()
    box: Gtk.Box = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    thumbnail: Gtk.Overlay = Gtk.Template.Child()
    icon: Gtk.Image = Gtk.Template.Child()
    extension_label: Gtk.Label = Gtk.Template.Child()
    picture: Gtk.Picture = Gtk.Template.Child()
    play_button: Gtk.Box = Gtk.Template.Child()

    dir_thumbnails: Gtk.Box = Gtk.Template.Child()
    dir_thumbnail_1: Gtk.Box = Gtk.Template.Child()
    dir_thumbnail_2: Gtk.Box = Gtk.Template.Child()
    dir_thumbnail_3: Gtk.Box = Gtk.Template.Child()

    item: Gtk.ListItem
    file_info: Gio.FileInfo

    path: Path
    gfile: Gio.File
    is_dir: bool
    content_type: str
    extension: str
    color: str
    thumbnail_path: str

    _gicon: str
    _display_name: str

    def __init__(self, item, **kwargs) -> None:
        super().__init__(**kwargs)
        self.item = item
        self.__zoom(None, shared.state_schema.get_uint("zoom-level"))
        shared.postmaster.connect("zoom", self.__zoom)

        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", self.__right_click)
        self.add_controller(right_click)

        middle_click = Gtk.GestureClick(button=Gdk.BUTTON_MIDDLE)
        middle_click.connect("pressed", self.__middle_click)
        self.add_controller(middle_click)

    def bind(self) -> None:
        """Build the icon after the object has been bound."""
        self.file_info = self.item.get_item()

        self.gfile = self.file_info.get_attribute_object("standard::file")
        self.gicon = self.file_info.get_symbolic_icon()
        self.content_type = self.file_info.get_content_type()
        self.color = get_color_for_content_type(self.content_type, self.gicon)
        display_name = self.file_info.get_display_name()
        self.is_dir = self.content_type == "inode/directory"
        self.display_name = display_name if self.is_dir else Path(display_name).stem
        self.extension = None if self.is_dir else Path(display_name).suffix[1:].upper()
        self.thumbnail_path = self.file_info.get_attribute_byte_string(
            Gio.FILE_ATTRIBUTE_THUMBNAIL_PATH
        )

        shared.drawing += 1
        # TODO: This seems to only prioritize directories.
        # What's up with that? Does it still work for them?
        if self.get_mapped():
            self.__build()
            return

        GLib.timeout_add(shared.drawing * 2, self.__build)

    def unbind(self) -> None:
        """Cleanup after the object has been unbound from its item."""
        self.icon.set_css_classes(["large-icons"])
        self.thumbnail.set_css_classes(["item-thumbnail"])
        self.extension_label.set_css_classes(["file-extension"])

    def __build(self) -> None:
        self.play_button.set_visible(False)

        if self.is_dir:
            self.__build_dir_thumbnail()
        else:
            self.__build_file_thumbnail()

        shared.drawing -= 1

    def __file_thumb_done(self, failed: bool) -> None:
        self.icon.set_visible(failed)
        self.picture.set_visible(not failed)

        if failed:
            self.icon.add_css_class(self.color + "-icon")
            self.thumbnail.add_css_class(self.color + "-background")
            self.extension_label.add_css_class(self.color + "-extension")
            return

        self.thumbnail.add_css_class("gray-background")
        self.extension_label.add_css_class(self.color + "-extension-thumb")

    def __build_file_thumbnail(self) -> None:
        if self.extension:
            self.extension_label.set_label(self.extension)
            self.extension_label.set_visible(True)
        else:
            self.extension_label.set_visible(False)

        if self.thumbnail_path:
            self.__thumb_cb(Gdk.Texture.new_from_filename(self.thumbnail_path))
            return

        GLib.Thread.new(
            None,
            generate_thumbnail,
            self.gfile,
            self.content_type,
            self.__thumb_cb,
        )

    def __dir_children_cb(self, gfile: Gio.File, result: Gio.Task) -> None:
        try:
            files = gfile.enumerate_children_finish(result)
        except GLib.Error:
            self.picture.set_paintable(shared.closed_folder_texture)
            return

        def next_files_cb(enumerator, result, index):
            try:
                files_list = enumerator.next_files_finish(result)
            except GLib.Error:
                if not index:
                    self.picture.set_paintable(shared.closed_folder_texture)
                return

            try:
                file_info = files_list[0]
            except IndexError:
                if not index:
                    self.picture.set_paintable(shared.closed_folder_texture)
                return

            if index == 3:
                return

            if not (content_type := file_info.get_content_type()):
                return

            match index:
                case 0:
                    thumbnail = self.dir_thumbnail_1
                    thumbnail.set_visible(True)
                case 1:
                    thumbnail = self.dir_thumbnail_2
                    thumbnail.set_visible(True)
                case 2:
                    thumbnail = self.dir_thumbnail_3
                    thumbnail.set_visible(True)

            index += 1
            files.next_files_async(1, GLib.PRIORITY_DEFAULT, None, next_files_cb, index)

            self.picture.set_paintable(shared.open_folder_texture)

            if gicon := file_info.get_symbolic_icon():
                thumbnail.get_child().set_from_gicon(gicon)

            if content_type == "inode/directory":
                thumbnail.add_css_class("light-blue-background")
                thumbnail.get_child().add_css_class("white-icon")
                return

            thumbnail.add_css_class("white-background")

            color = get_color_for_content_type(content_type, gicon)
            thumbnail.get_child().add_css_class(color + "-icon-light-only")

            if thumbnail_path := file_info.get_attribute_byte_string(
                Gio.FILE_ATTRIBUTE_THUMBNAIL_PATH
            ):
                picture = Gtk.Picture.new_for_filename(thumbnail_path)
                picture.set_content_fit(Gtk.ContentFit.COVER)
                thumbnail.get_child().set_visible(False)
                thumbnail.add_overlay(picture)
                return

            # HACK: I don't know how else to get a GFile for file_info
            child_gfile = gfile.get_child(file_info.get_name())

            GLib.Thread.new(
                None,
                generate_thumbnail,
                child_gfile,
                content_type,
                self.__dir_thumb_cb,
                thumbnail,
            )

        # TODO: Could be oprimized if I called next_files with 3 the first time
        files.next_files_async(1, GLib.PRIORITY_DEFAULT, None, next_files_cb, 0)

    def __build_dir_thumbnail(self) -> None:
        self.extension_label.set_visible(False)
        self.picture.set_visible(True)
        self.icon.set_visible(False)

        self.picture.set_content_fit(Gtk.ContentFit.FILL)
        self.thumbnail.add_css_class(self.color + "-background")

        self.gfile.enumerate_children_async(
            ",".join(
                (
                    Gio.FILE_ATTRIBUTE_STANDARD_SYMBOLIC_ICON,
                    Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
                    Gio.FILE_ATTRIBUTE_THUMBNAIL_PATH,
                    Gio.FILE_ATTRIBUTE_STANDARD_NAME,
                )
            ),
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT,
            None,
            self.__dir_children_cb,
        )

    def __dir_thumb_cb(
        self,
        texture: Optional[Gdk.Texture] = None,
        thumbnail: Optional[Gtk.Overlay] = None,
        failed: Optional[bool] = False,
    ) -> None:
        if failed:
            return

        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        thumbnail.get_child().set_visible(False)
        thumbnail.add_overlay(picture)

    def __thumb_cb(
        self,
        texture: Optional[Gdk.Texture] = None,
        failed: Optional[bool] = False,
    ) -> None:
        if failed:
            GLib.idle_add(self.__file_thumb_done, failed)
            return
        self.__file_thumb_done(failed)

        self.picture.set_paintable(texture)

        if self.content_type.split("/")[0] not in ("video", "audio"):
            return

        self.play_button.set_visible(True)

    def __zoom(self, _obj: Any, zoom_level: int) -> None:
        self.clamp.set_maximum_size(50 * zoom_level)
        self.box.set_margin_start(4 * zoom_level)
        self.box.set_margin_end(4 * zoom_level)
        self.box.set_margin_top(4 * zoom_level)
        self.box.set_margin_bottom(4 * zoom_level)

        match zoom_level:
            case 1:
                self.thumbnail.set_size_request(96, 80)
            case 2:
                self.thumbnail.set_size_request(96, 96)
            case _:
                self.thumbnail.set_size_request(40 * zoom_level, 32 * zoom_level)

        if zoom_level < 3:
            self.dir_thumbnails.set_spacing(12)
            self.dir_thumbnails.set_margin_start(10)
            self.dir_thumbnails.set_margin_top(6)
        elif zoom_level < 4:
            self.dir_thumbnails.set_spacing(6)
            self.dir_thumbnails.set_margin_start(6)
            self.dir_thumbnails.set_margin_top(6)
        elif zoom_level < 5:
            self.dir_thumbnails.set_spacing(9)
            self.dir_thumbnails.set_margin_start(8)
            self.dir_thumbnails.set_margin_top(8)
        else:
            self.dir_thumbnails.set_spacing(9)
            self.dir_thumbnails.set_margin_start(7)
            self.dir_thumbnails.set_margin_top(7)

        if zoom_level < 4:
            self.dir_thumbnail_1.set_size_request(32, 32)
            self.dir_thumbnail_2.set_size_request(32, 32)
            self.dir_thumbnail_3.set_size_request(32, 32)
        elif zoom_level < 5:
            self.dir_thumbnail_1.set_size_request(42, 42)
            self.dir_thumbnail_2.set_size_request(42, 42)
            self.dir_thumbnail_3.set_size_request(42, 42)
        else:
            self.dir_thumbnail_1.set_size_request(56, 56)
            self.dir_thumbnail_2.set_size_request(56, 56)
            self.dir_thumbnail_3.set_size_request(56, 56)

        if zoom_level < 2:
            self.icon.set_pixel_size(20)
            self.icon.set_icon_size(Gtk.IconSize.INHERIT)
        else:
            self.icon.set_pixel_size(-1)
            self.icon.set_icon_size(Gtk.IconSize.LARGE)

    def __select_self(self) -> None:
        if not (
            multi_selection := self.get_parent().get_parent().get_model()
        ).is_selected(pos := self.item.get_position()):
            multi_selection.select_item(pos, True)

    def __right_click(self, *_args: Any) -> None:
        self.__select_self()

        menu_items = {"rename", "copy", "cut", "trash", "open"}
        if self.is_dir:
            menu_items.add("open-new-tab")
            menu_items.add("open-new-window")
        if self.gfile.get_uri().startswith("trash://"):
            menu_items.remove("trash")
            menu_items.add("trash-restore")
            menu_items.add("trash-delete")

        self.get_root().set_menu_items(menu_items)

    def __middle_click(self, *_args: Any) -> None:
        self.__select_self()

        win = self.get_root()
        for gfile in win.get_gfiles_from_positions(win.get_selected_items()):
            win.new_tab(gfile)

    @GObject.Property(type=str)
    def display_name(self) -> str:
        """The name of the item visible to the user."""
        return self._display_name

    @display_name.setter
    def set_display_name(self, name: str) -> None:
        self._display_name = name

    @GObject.Property(type=Gio.Icon)
    def gicon(self) -> Gio.Icon:
        """The icon of the item displayed to the user if no thumbnail is available."""
        return self._gicon

    @gicon.setter
    def set_gicon(self, gicon: Gio.Icon) -> None:
        self._gicon = gicon
