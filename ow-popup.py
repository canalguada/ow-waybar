#!/usr/bin/env python3

import json
import os
import stat
import subprocess
import sys
import argparse
from datetime import datetime

try:
    import requests
except ModuleNotFoundError:
    print("You need to install python-requests package", file=sys.stderr)
    sys.exit(1)

from tools import (
    check_key,
    eprint,
    file_age,
    hms,
    load_json,
    save_json,
    temp_dir,
)

dir_name = os.path.dirname(__file__)

degrees = {"standard": "°K", "metric": "°C", "imperial": "°F"}

icons = {
    # clear
    800: "",  # clear sky
    # clouds
    801: "",  # few clouds: 11-25%
    802: "",  # scattered clouds: 25-50%
    803: "",  # broken clouds: 51-84%
    804: "",  # overcast clouds: 85-100%
    # drizzle
    300: "",  # light intensity drizzle
    301: "",  # drizzle
    302: "",  # heavy intensity drizzle
    310: "",  # light intensity drizzle rain
    311: "",  # drizzle rain
    312: "",  # heavy intensity drizzle rain
    313: "",  # shower rain and drizzle
    314: "",  # heavy shower rain and drizzle
    321: "",  # shower drizzle
    # rain
    500: "",  # light rain
    501: "",  # moderate rain
    502: "",  # heavy intensity rain
    503: "",  # very heavy rain
    504: "",  # extreme rain
    511: "",  # freezing rain
    520: "",  # light intensity shower rain
    521: "",  # shower rain
    522: "",  # heavy intensity shower rain
    531: "",  # ragged shower rain
    # thunderstorm
    200: "",  # thunderstorm with light rain
    201: "",  # thunderstorm with rain
    202: "",  # thunderstorm with heavy rain
    210: "",  # light thunderstorm
    211: "",  # thunderstorm
    212: "",  # heavy thunderstorm
    221: "",  # ragged thunderstorm
    230: "",  # thunderstorm with light drizzle
    231: "",  # thunderstorm with drizzle
    232: "",  # thunderstorm with heavy drizzle
    # snow
    600: "",  # light snow
    601: "",  # Snow
    602: "",  # Heavy snow
    611: "",  # Sleet
    612: "",  # Light shower sleet
    613: "",  # Shower sleet
    615: "",  # Light rain and snow
    616: "",  # Rain and snow
    620: "",  # Light shower snow
    621: "",  # Shower snow
    622: "",  # Heavy shower snow
    # atmosphere
    701: "",  # mist
    711: "",  # smoke
    721: "",  # haze
    731: "",  # sand/dust whirls
    741: "",  # fog
    751: "",  # sand
    761: "",  # dust
    762: "",  # volcanic ash
    771: "",  # sqalls
    781: "",  # tornado
}


def get_icon(id):
    return icons.get(id, "✨")


def direction(deg):
    if 0 <= deg <= 23 or 337 <= deg <= 360:
        return "N"
    elif 24 <= deg <= 68:
        return "NE"
    elif 69 <= deg <= 113:
        return "E"
    elif 114 <= deg <= 158:
        return "SE"
    elif 159 <= deg <= 203:
        return "S"
    elif 204 <= deg <= 248:
        return "SW"
    elif 249 <= deg <= 293:
        return "W"
    elif 293 <= deg <= 336:
        return "NW"
    else:
        return "WTF"


def join(*args: str, sep: str = " "):
    return sep.join(filter(lambda _: _, args))


def get_ow_property(data, name: str) -> str:
    match name:
        case "country":
            if name in data["sys"] and data["sys"][name]:
                return "{}".format(data["sys"][name])
        case "sunrise":
            if name in data["sys"] and data["sys"][name]:
                dt = datetime.fromtimestamp(data["sys"][name])
                return f'🌅 {dt.strftime("%H:%M")}'
        case "sunset":
            if name in data["sys"] and data["sys"][name]:
                dt = datetime.fromtimestamp(data["sys"][name])
                return f'🌇 {dt.strftime("%H:%M")}'
        case "icon":
            if "id" in data["weather"][0]:
                return get_icon(data["weather"][0]["id"])
        case "desc":
            if "description" in data["weather"][0]:
                return data["weather"][0]["description"].capitalize()
        case "temp":
            if name in data["main"] and (value := data["main"][name]):
                return value
        case "feels_like":
            if name in data["main"] and (value := data["main"][name]):
                return value
        case "humidity":
            if name in data["main"] and (value := data["main"][name]):
                return "{}%".format(value)
        case "pressure":
            if name in data["main"] and (value := data["main"][name]):
                return "{} hPa".format(value)
        case "wind_speed":
            if "wind" in data and "speed" in data["wind"]:
                return "{} m/s".format(data["wind"]["speed"])
        case "wind_dir":
            if "wind" in data and "deg" in data["wind"]:
                return "{}".format((direction(data["wind"]["deg"])))
        case "wind_gust":
            if "wind" in data and "gust" in data["wind"]:
                return "{} m/s".format(data["wind"]["gust"])
        case "clouds":
            if name in data and "all" in data[name]:
                return "{}%".format(data[name]["all"])
        case "visibility":
            if name in data:
                return "{} km".format(int(data[name] / 1000))
    return ""


def calling_funcname() -> str:
    return sys._getframe().f_back.f_code.co_name


class OpenWeather:
    def __init__(self, settings, voc):
        defaults = {
            "appid": "",
            "lat": 48.8583701,
            "long": 2.2944813,
            "lang": "fr",
            "units": "metric",
            "interval": 1800,
            "loc-name": "Paris",
            "show-name": False,
            "popup-text-size": "medium",
            "popup-forecast-size": "small",
            "show-humidity": False,
            "show-wind": False,
            "show-pressure": False,
            "show-cloudiness": False,
            "show-visibility": False,
            "show-pop": False,
            "show-volume": False,
            "module-id": "owm",
        }

        for key in defaults:
            check_key(settings, key, defaults[key])

        self.settings = settings
        self.lang = voc

        self.weather = None
        self.forecast = None

        tmp_dir = temp_dir()
        self.weather_file = "{}-{}".format(
            os.path.join(tmp_dir, "ow-weather"), settings["module-id"]
        )
        self.forecast_file = "{}-{}".format(
            os.path.join(tmp_dir, "ow-forecast"), settings["module-id"]
        )
        eprint("Weather file: {}".format(self.weather_file))
        eprint("Forecast file: {}".format(self.forecast_file))

        if not settings["lat"] or not settings["long"]:
            # Set dummy location
            eprint("Coordinates not set, setting Eiffel Tower in Paris, France")
            settings["lat"] = 48.8583701
            settings["long"] = 2.2944813

        eprint("Latitude: {}".format(settings["lat"]))
        eprint("Longitude: {}".format(settings["long"]))

        self.weather_request = "https://api.openweathermap.org/data/2.5/weather?lat={}&lon={}&units={}&lang={}&appid={}".format(
            settings["lat"],
            settings["long"],
            settings["units"],
            settings["lang"],
            settings["appid"],
        )

        self.forecast_request = "https://api.openweathermap.org/data/2.5/forecast?lat={}&lon={}&units={}&lang={}&appid={}".format(
            settings["lat"],
            settings["long"],
            settings["units"],
            settings["lang"],
            settings["appid"],
        )

        self.id = 800
        self.label = ""
        self.popup = ""

    def get_data(self):
        self.get_weather()
        self.get_forecast()
        self.update_widget()

    def get_weather(self):
        if not os.path.isfile(self.weather_file) or int(
            file_age(self.weather_file) > self.settings["interval"] - 1
        ):
            eprint(hms(), "Requesting weather data")
            try:
                r = requests.get(self.weather_request)
                self.weather = json.loads(r.text)
                if self.weather["cod"] in ["200", 200]:
                    save_json(self.weather, self.weather_file)
            except Exception as e:
                self.weather = None
                eprint(e)
        elif not self.weather:
            eprint(hms(), "Loading weather data from file")
            self.weather = load_json(self.weather_file)

    def get_forecast(self):
        if not os.path.isfile(self.forecast_file) or int(
            file_age(self.forecast_file) > self.settings["interval"] - 1
        ):
            eprint(hms(), "Requesting forecast data")
            try:
                r = requests.get(self.forecast_request)
                self.forecast = json.loads(r.text)
                if self.forecast["cod"] in ["200", 200]:
                    save_json(self.forecast, self.forecast_file)
            except Exception as e:
                self.forecast = None
                eprint(e)
        elif not self.forecast:
            eprint(hms(), "Loading forecast data from file")
            self.forecast = load_json(self.forecast_file)

    def update_widget(self):
        if self.weather and self.weather["cod"] and self.weather["cod"] in [200, "200"]:
            row = []
            if "id" in self.weather["weather"][0]:
                new_id = self.weather["weather"][0]["id"]
                if self.id != new_id:
                    self.id = new_id
                row.append(get_icon(self.id))

            if "name" in self.weather and self.settings["show-name"]:
                row.append(
                    self.weather["name"]
                    if not self.settings["loc-name"]
                    else self.settings["loc-name"]
                )

            if "temp" in self.weather["main"] and self.weather["main"]["temp"]:
                deg = degrees[self.settings["units"]]
                try:
                    val = round(float(self.weather["main"]["temp"]), 1)
                    temp = "{}{}".format(str(val), deg)
                    row.append(temp)
                except:
                    pass

            self.label = " ".join(row)
            self.popup = self.display_popup()

    @property
    def loc_label(self) -> str:
        return (
            self.weather["name"]
            if "name" in self.weather and not self.settings["loc-name"]
            else self.settings["loc-name"]
        )

    @property
    def country(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "({})".format(s)

    @property
    def gps(self) -> str:
        return "({}, {})".format(self.settings["lat"], self.settings["long"])

    @property
    def sunrise(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return s

    @property
    def sunset(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return s

    @property
    def icon(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return s

    @property
    def desc(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return s

    @property
    def temp(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "{}{}".format(
                str(round(float(s), 1)), degrees[self.settings["units"]]
            )

    @property
    def feels_like(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "{}: {}°".format(self.lang["feels-like"], str(round(float(s), 1)))

    @property
    def humidity(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "{}: {}".format(self.lang["humidity"], s)

    @property
    def pressure(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "{}: {}".format(self.lang["pressure"], s)

    @property
    def wind_speed(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "{}: {}".format(self.lang["wind"], s)

    @property
    def wind_dir(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return s

    @property
    def wind_gust(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "({} {})".format(self.lang["gust"], s)

    @property
    def clouds(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "{}: {}".format(self.lang["cloudiness"], s)

    @property
    def visibility(self) -> str:
        if s := get_ow_property(self.weather, calling_funcname()):
            return "{}: {}".format(self.lang["visibility"], s)

    def display_popup(self):
        if (
            not self.weather
            or not self.weather["cod"] in ["200", 200]
            or not self.forecast["cod"] in ["200", 200]
        ):
            print("No data available")
            return

        rows = []
        span = '<span font_size="{}">{}</span>'
        # Big icon
        rows.append(span.format("xx-large", join(self.icon, self.temp)))
        # Weather details
        for row in [
            join(self.desc, self.feels_like, sep=" - "),
            join(self.pressure, self.humidity, sep=" - "),
            join(self.wind_speed, self.wind_dir, self.wind_gust),
            join(self.clouds, self.visibility, sep=" - "),
        ]:
            if row:
                rows.append(span.format(self.settings["popup-text-size"], row))
        # FORECAST
        if self.forecast["cod"] in [200, "200"]:
            timefmt = "%A %-e %B"
            curday = ""
            cursize = self.settings["popup-forecast-size"]
            for i in range(len(self.forecast["list"])):
                if i > 31:
                    break
                data = self.forecast["list"][i]
                # Date
                dt = datetime.fromtimestamp(data["dt"]).strftime(timefmt)
                if curday != dt:
                    curday = dt
                    rows.append(
                        '<span font_size="{}" weight="bold" color="cyan">\n{}</span>'.format(
                            cursize, curday
                        )
                    )
                items = []
                # Time
                dt = datetime.fromtimestamp(data["dt"]).strftime("<b>%H:%M</b>")
                items.append(
                    '<span font_size="{}" color="orange"><tt>{}</tt></span>'.format(
                        "x-small", dt
                    )
                )
                # Icon
                if "weather" in data and data["weather"][0]:
                    values = [get_ow_property(data, name) for name in ["icon", "desc"]]
                    items.append(span.format(cursize, join(*values, sep="  ")))
                # Temperature
                values = [
                    "{}°".format(str(int(round(value, 0))))
                    for name in ["temp", "feels_like"]
                    if (value := get_ow_property(data, name))
                ]
                if values[1]:
                    values[1] = "({})".format(values[1])
                items.append(span.format(cursize, join(*values)))
                # Humidity
                if self.settings["show-humidity"] and (
                    value := get_ow_property(data, "humidity")
                ):
                    items.append(
                        '💦 <span font_size="{}">{}%</span>'.format(cursize, value)
                    )
                # Wind
                if self.settings["show-wind"]:
                    values = [
                        get_ow_property(data, name)
                        for name in ["wind_speed", "wind_dir", "wind_gust"]
                    ]
                    if values[2]:
                        values[2] = "({})".format(values[2])
                    if content := join(*values):
                        items.append(("🌬 " + span).format(cursize, content))
                # Pressure
                if self.settings["show-pressure"] and (
                    value := get_ow_property(data, "pressure")
                ):
                    items.append(("🎈 " + span).format(cursize, value))
                # Cloudiness
                if self.settings["show-cloudiness"] and (
                    value := get_ow_property(data, "clouds")
                ):
                    items.append(("☁ " + span).format(cursize, value))
                # Visibility
                if self.settings["show-visibility"] and (
                    value := get_ow_property(data, "visibility")
                ):
                    items.append(("👁 " + span).format(cursize, value))
                # Probability of precipitation
                if self.settings["show-pop"] and "pop" in data and data["pop"]:
                    items.append(
                        '☔ <span font_size="{}">{}%</span>'.format(
                            cursize, int(round(data["pop"] * 100, 0))
                        )
                    )
                # Precipitation volume
                if self.settings["show-volume"]:
                    if "rain" in data and "3h" in data["rain"]:
                        items.append(
                            '📏 <span font_size="{}">{} mm</span>'.format(
                                cursize, round(data["rain"]["3h"], 2)
                            )
                        )

                    if "snow" in data and "3h" in data["snow"]:
                        items.append(
                            '<span font_size="{}">{} mm</span>'.format(
                                cursize, round(data["snow"]["3h"], 2)
                            )
                        )
                rows.append(" ".join(items))
        rows.append(
            '<span size="{}" weight="bold">\n{}</span>'.format(
                self.settings["popup-forecast-size"],
                join(self.loc_label, self.country, self.sunrise, self.sunset),
            )
        )
        if os.path.isfile(self.forecast_file):
            mtime = datetime.fromtimestamp(os.stat(self.forecast_file)[stat.ST_MTIME])
            rows.append(
                '<span font_size="{}">{}</span>'.format(
                    self.settings["popup-forecast-size"],
                    join(self.gps, mtime.strftime("%d %B %H:%M:%S")),
                )
            )
        return "\n".join(rows)


def main(**kwargs):
    settings = (
        {
            "popup-text-size": "medium",
            "popup-forecast-size": "small",
            "interval": 1800,
            "loc-name": kwargs.get("city_name", ""),
        }
        | {
            "appid": kwargs.get("appid", ""),
            "lat": kwargs.get("lat", 0.0),
            "long": kwargs.get("lon", 0.0),
            "lang": kwargs.get("lang", "fr"),
            "units": kwargs.get("units", "metric"),
        }
        | {
            f"show-{k}": kwargs.get(f"show_{k}", False)
            for k in [
                "name",
                "humidity",
                "wind",
                "pressure",
                "cloudiness",
                "visibilty",
                "pop",
                "volume",
            ]
        }
    )
    voc = load_json(
        os.path.join(
            dir_name, "fr_FR.json" if settings["lang"] == "fr" else "en_US.json"
        )
    )
    executor = OpenWeather(settings, voc)
    executor.get_data()
    print(
        json.dumps(
            {"text": executor.label, "alt": executor.label, "tooltip": executor.popup}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        add_help=True, description="Openweather custom module for Waybar"
    )
    parser.add_argument(
        "--appid",
        action="store",
        required=True,
        default=None,
        help="Openweather API key",
    )
    parser.add_argument("--lat", type=float, default=48.8583701, help="GPS latitude")
    parser.add_argument("--lon", type=float, default=2.2944813, help="GPS longitude")
    parser.add_argument("--lang", choices=["en", "fr"], default="fr", help="Language")
    parser.add_argument(
        "--units", choices=["metric", "imperial"], default="metric", help="Units"
    )
    for k in [
        "name",
        "humidity",
        "wind",
        "pressure",
        "cloudiness",
        "visibilty",
        "pop",
        "volume",
    ]:
        parser.add_argument(f"--show-{k}", action="store_true", help=f"Show {k}")
    try:
        args = parser.parse_args()
        main(**vars(args))
    except SystemExit as exception:
        pass

# vim: set ft=python fdm=indent ts=4 sw=4 et:
