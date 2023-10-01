#!/usr/bin/env python3

import os
import sys
import json
import subprocess
import stat
import time
import threading

import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk, Gdk, GdkPixbuf
from shutil import copyfile
from datetime import datetime

try:
    import psutil
except:
    pass


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def temp_dir():
    if os.getenv("TMPDIR"):
        return os.getenv("TMPDIR")
    elif os.getenv("TEMP"):
        return os.getenv("TEMP")
    elif os.getenv("TMP"):
        return os.getenv("TMP")

    return "/tmp"


def get_app_dirs():
    desktop_dirs = []

    home = os.getenv("HOME")
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    xdg_data_dirs = (
        os.getenv("XDG_DATA_DIRS")
        if os.getenv("XDG_DATA_DIRS")
        else "/usr/local/share/:/usr/share/"
    )

    if xdg_data_home:
        desktop_dirs.append(os.path.join(xdg_data_home, "applications"))
    else:
        if home:
            desktop_dirs.append(os.path.join(home, ".local/share/applications"))

    for d in xdg_data_dirs.split(":"):
        desktop_dirs.append(os.path.join(d, "applications"))

    # Add flatpak dirs if not found in XDG_DATA_DIRS
    flatpak_dirs = [
        os.path.join(home, ".local/share/flatpak/exports/share/applications"),
        "/var/lib/flatpak/exports/share/applications",
    ]
    for d in flatpak_dirs:
        if d not in desktop_dirs:
            desktop_dirs.append(d)

    return desktop_dirs


def copy_files(src_dir, dst_dir, restore=False):
    src_files = os.listdir(src_dir)
    for file in src_files:
        if os.path.isfile(os.path.join(src_dir, file)):
            if not os.path.isfile(os.path.join(dst_dir, file)) or restore:
                copyfile(os.path.join(src_dir, file), os.path.join(dst_dir, file))
                print("Copying '{}'".format(os.path.join(dst_dir, file)))


def copy_executors(src_dir, dst_dir):
    src_files = os.listdir(src_dir)
    for file in src_files:
        if os.path.isfile(os.path.join(src_dir, file)) and not os.path.isfile(
            os.path.join(dst_dir, file)
        ):
            copyfile(os.path.join(src_dir, file), os.path.join(dst_dir, file))
            print(
                "Copying '{}', marking executable".format(os.path.join(dst_dir, file))
            )
            st = os.stat(os.path.join(dst_dir, file))
            os.chmod(os.path.join(dst_dir, file), st.st_mode | stat.S_IEXEC)


def load_text_file(path):
    try:
        with open(path, "r") as file:
            data = file.read()
            return data
    except Exception as e:
        print(e)
        return None


def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        eprint("Error loading json: {}".format(e))
        return {}


def save_json(src_dict, path):
    try:
        with open(path, "w") as f:
            json.dump(src_dict, f, indent=2)
        return "ok"
    except Exception as e:
        return e


def save_string(string, file):
    try:
        file = open(file, "wt")
        file.write(string)
        file.close()
    except:
        print("Error writing file '{}'".format(file))


def load_string(path):
    try:
        with open(path, "r") as file:
            data = file.read()
            return data
    except:
        return ""


def check_key(dictionary, key, default_value):
    """
    Adds a key w/ default value if missing from the dictionary
    """
    if key not in dictionary:
        dictionary[key] = default_value


def cmd2string(cmd):
    process_env = dict(os.environ)
    process_env.update({"LANG": "C.UTF-8"})
    try:
        return (
            subprocess.check_output(cmd, shell=True, env=process_env)
            .decode("utf-8")
            .strip()
        )
    except subprocess.CalledProcessError:
        return ""


def is_command(cmd):
    cmd = cmd.split()[0]  # strip arguments
    cmd = "command -v {}".format(cmd)
    try:
        is_cmd = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        if is_cmd:
            return True

    except subprocess.CalledProcessError:
        pass

    return False


def create_background_task(target, interval, args=(), kwargs=None):
    if kwargs is None:
        kwargs = {}

    def loop_wrapper():
        if interval > 0:
            while True:
                target(*args, **kwargs)
                time.sleep(interval)
        else:
            target(*args, **kwargs)

    thread = threading.Thread(target=loop_wrapper, daemon=True)
    return thread


def seconds2string(seconds):
    minutes, sec = divmod(seconds, 60)
    hrs, minutes = divmod(minutes, 60)

    hrs = str(hrs)
    if len(hrs) < 2:
        hrs = "0{}".format(hrs)

    minutes = str(minutes)
    if len(minutes) < 2:
        minutes = "0{}".format(minutes)

    return "{}:{}".format(hrs, minutes)


def update_image(image, icon_name, icon_size, icons_path="", fallback=True):
    scale = image.get_scale_factor()
    icon_size *= scale
    pixbuf = create_pixbuf(icon_name, icon_size, icons_path, fallback)
    surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, image.get_window())
    image.set_from_surface(surface)


def update_image_fallback_desktop(
    image, icon_name, icon_size, icons_path, fallback=True
):
    try:
        # This should work if your icon theme provides the icon, or if it's placed in /usr/share/pixmaps
        update_image(image, icon_name, icon_size, fallback=False)
    except:
        # If the above fails, let's search .desktop files to find the icon name
        icon_from_desktop = get_icon_name(icon_name)
        if icon_from_desktop:
            # trim extension, if given and the definition is not a path
            if "/" not in icon_from_desktop:
                icon_from_desktop = os.path.splitext(icon_from_desktop)[0]

            update_image(
                image, icon_from_desktop, icon_size, icons_path, fallback=fallback
            )


def update_gtk_entry(entry, icon_pos, icon_name, icon_size, icons_path=""):
    scale = entry.get_scale_factor()
    icon_size *= scale
    pixbuf = create_pixbuf(icon_name, icon_size, icons_path)
    entry.set_icon_from_pixbuf(icon_pos, pixbuf)


def create_pixbuf(icon_name, icon_size, icons_path="", fallback=True):
    try:
        # In case a full path was given
        if icon_name.startswith("/"):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                icon_name, icon_size, icon_size
            )
        else:
            icon_theme = Gtk.IconTheme.get_default()
            if icons_path:
                search_path = icon_theme.get_search_path()
                search_path.append(icons_path)
                icon_theme.set_search_path(search_path)

            try:
                if icons_path:
                    path = "{}/{}.svg".format(icons_path, icon_name)
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        path, icon_size, icon_size
                    )
                else:
                    raise ValueError("icons_path not supplied.")
            except:
                try:
                    pixbuf = icon_theme.load_icon(
                        icon_name, icon_size, Gtk.IconLookupFlags.FORCE_SIZE
                    )
                except:
                    pixbuf = icon_theme.load_icon(
                        icon_name.lower(), icon_size, Gtk.IconLookupFlags.FORCE_SIZE
                    )
    except Exception as e:
        if fallback:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                os.path.join(get_config_dir(), "icons_light/icon-missing.svg"),
                icon_size,
                icon_size,
            )
        else:
            raise e
    return pixbuf


def get_cache_dir():
    if os.getenv("XDG_CACHE_HOME"):
        return os.getenv("XDG_CACHE_HOME")
    elif os.getenv("HOME") and os.path.isdir(os.path.join(os.getenv("HOME"), ".cache")):
        return os.path.join(os.getenv("HOME"), ".cache")
    else:
        return None


def file_age(path):
    return time.time() - os.stat(path)[stat.ST_MTIME]


def hms():
    return datetime.fromtimestamp(time.time()).strftime("%H:%M:%S")

