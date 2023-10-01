#!/bin/bash

APPID="<Your Openweather API key>"
LAT="<GPS latitude>"
LON="<GPS logitude>"

${0%/*}/ow-popup.py --appid $APPID --lat $LAT --lon $LON "$@"
