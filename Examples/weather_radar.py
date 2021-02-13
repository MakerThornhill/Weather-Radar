"""
--------------------------------------------------
  Weather Radar! --  Example code

  (by @Maker.Thornhill)
  https://hackaday.io/project/176547-weather-radar
--------------------------------------------------

Howdy! This is the more simplified version of my Weather Radar! code, demostrating
how I obtain National Weather Service radar images and merge them with basemaps generated
using the GeoTiler library.

While I show how I get NWS hazard and warning polygons, this example code doesn't include
how to get OpenWeather data (you can find more info here: https://openweathermap.org/api/one-call-api).

"""

import time
from datetime import datetime
import pytz

import os
import json
import math
import requests
import logging

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import xmltodict
import geotiler
import numpy as np

#Adafruit & CircuitPython libraries
import board
import digitalio
import adafruit_rgb_display.ili9341 as ili9341

#Secrets! (openweather API & lat long coordinates)
from secrets import secrets

CURR_DIR = f"{os.path.dirname(__file__)}/"

cs_pin = digitalio.DigitalInOut(board.CE0)
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = digitalio.DigitalInOut(board.D24)
BAUDRATE = 24000000
spi = board.SPI()
disp = ili9341.ILI9341(
    spi,
    rotation=270,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
)

print("\n************************************\n*  WEATHER RADAR by Thornhill!     *\n************************************")

# Open and display the loading screen!
loading = Image.open(f"{CURR_DIR}loading.png")
disp.image(loading)

################################################
# Get nearest station based on Lat Long
################################################
def get_station_data(station_param=None):
    ''' Get Radar station data from Weather API.
        Param station_param: Station ID (if known)

        Returns the status of the radar station (Up, Warning, Down)
    '''
    global station
    global layer
    global zoom
    global legend
    global station_mode
    global station_status
    global latency

    ######################
    # Get the station ID #
    ######################
    if station_param in ["",None]:
        station = location_to_station()
    else:
        station = station_param

    ################################
    # Get radar stations JSON file #
    ################################
    stations_url = "https://api.weather.gov/radar/stations?stationType=WSR-88D,TDWR"

    try:
        response = requests.get(stations_url, headers=headers, timeout=20)
    except:
        print("Connection Problems: Getting radar station data")
        response = False

    if response:
        station_file = response.json()
    else:
        print(f"Couldn't get the station file ({response})")
        station_status = f"{response}"
        return station_status

    ################################
    # Get the current time (in UTC) #
    ################################
    UTC = pytz.utc
    datetime_utc = datetime.now(UTC)

    #########################################
    # Pull the data we need for our station #
    #########################################
    for record in station_file['features']:
        if record['properties']['id'] == station.upper(): #If the ID matches
            station_name = record['properties']['name']
            station_mode = record['properties']['rda']['properties']['volumeCoveragePattern'] #Mode of the station (e.g. R35, R21)

            #Check the status of the station by looking at the last received time.
            latency_time = datetime.strptime(record['properties']['latency']['levelTwoLastReceivedTime'],'%Y-%m-%dT%H:%M:%S%z')
            diff_time = datetime_utc - latency_time

            if diff_time.days > 0: #If greater than 1 day, then it's definitely down
                station_status = "Down"
            else:
                if diff_time.seconds < (60*10): #Less than 10 mins, it's probably up!
                    station_status = "Up"
                elif diff_time.seconds > (60*10) and diff_time.seconds < (60*60): #Between 10 mins & 60, warning!
                    station_status = "Warning"
                else: #Otherwise, yeah, it's down
                    station_status = "Down"

            latency = round(diff_time.seconds/60,1)

            print(f"\n----------------------\nStation: {station.upper()} ({station_name})\n----------------------")
            print(f"- Mode: {station_mode}")
            print(f"- Status: {station_status} (Last received: {latency} minutes ago)")

    return station_status
def location_to_station():
    ''' Get the ID of the nearest radar station from lat long coordinates.
        Also nearest population centre, state, time zone, and forecast URLs

        Returns the station code! (must be lowercase)
    '''
    global station
    global forecast_url
    global forecast_grid_url
    global timeZone

    ######################################
    # Try to get the lat long point file #
    ######################################
    point_url = f"https://api.weather.gov/points/{lat_long[0]},{lat_long[1]}"

    try:
        response = requests.get(point_url, headers=headers, timeout=5)
    except:
        print("Connection Problems getting Lat/Long point data!")
        response = False

    if response:
        point_file = json.load(BytesIO(response.content))
        point_file = point_file['properties']

        station = point_file['radarStation'].lower()
        location_city = point_file['relativeLocation']['properties']['city']
        location_state = point_file['relativeLocation']['properties']['state']
        timeZone = point_file['timeZone']
        forecast_url = point_file['forecast']

        print(f"{location_city} ({location_state}) -- {station.upper()} -- {timeZone}")
    else:
        print(f"Unable to get location or radar ({response})")
        get_station_data(secrets["station"]) #Use a fallback if it doesn't work!

    return station
def get_bounding_coordinates(url):
    ''' Get and return the bounding coordinates of a WMS layer.
        Param url: The url to the GetCapabilities xml

        Returns minx, miny, maxx, maxy

    '''

    ################################
    # Get the GetCapabilities file #
    ################################
    try:
        response = requests.get(url, headers=headers, timeout=5 )
    except:
        print("Connection Problems: Getting Bounding coordinates")
        response = False

    ################################
    # Get the bounding coordinates #
    ################################
    if response:
        xml_file = BytesIO(response.content)
        capabilties_dict = xmltodict.parse(xml_file.read()) #Parse the XML into a dictionary
        bounding_coordinates = capabilties_dict["WMS_Capabilities"]["Capability"]["Layer"]["EX_GeographicBoundingBox"]

        minx = bounding_coordinates['westBoundLongitude']
        maxx = bounding_coordinates['eastBoundLongitude']
        miny = bounding_coordinates['southBoundLatitude']
        maxy = bounding_coordinates['northBoundLatitude']
        return minx, miny, maxx, maxy
    else:
        print(f"Couldn't get GetCapabilities file ({response})")
        return 0, 0, 0, 0

lat_long = secrets['coordinates']
headers = secrets['header']
layer = 'bohp'

location_to_station()

################################################
# XML & JSON urls
################################################
capabilities_url = f'https://opengeo.ncep.noaa.gov:443/geoserver/{station}/{station}_{layer}/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities'
warnings_capabilities_url = "https://opengeo.ncep.noaa.gov/geoserver/wwa/warnings/ows?service=wms&version=1.3.0&request=GetCapabilities"
alert_capabilities_url = "https://opengeo.ncep.noaa.gov/geoserver/wwa/hazards/ows?service=wms&version=1.3.0&request=GetCapabilities"

#Get the SW and NE coordinates from the WMS GetCapabilities file
minx, miny, maxx, maxy = get_bounding_coordinates(capabilities_url)

################################################
# WMS settings
################################################
format = 'image%2Fpng'
bg_colour = 0xFFFFFF
transparent=True
TIME = "TIME=2020-11-10T20%3A17%3A50.000Z"
EPSG = 4326
SRS = f"EPSG%3A{EPSG}"
EXCEPTION = "application/vnd.ogc.se_inimage"

################################################
# Fonts!
################################################

fnt_medium = ImageFont.truetype(f"{CURR_DIR}HelveticaNeue.ttf", 15)
fnt_goth = ImageFont.truetype(f"{CURR_DIR}CenturyGothic.ttf", 20)
fnt_goth_bold = ImageFont.truetype(f"{CURR_DIR}CenturyGothic-Bold.ttf", 20)
fnt_goth_medium = ImageFont.truetype(f"{CURR_DIR}CenturyGothic.ttf", 15)


################################################
#  FUNCTIONS!
################################################
def get_radar_images(base_map_layer='stamen-toner',layer=None, zoom=None, show_alerts=True, warnings_list=[],hazard_list=[], frames=None):
    ''' Get and make a list of radar images.

        Param base_map_layer (str): basemap layer to use (see geotiler library for map providers)
        Param layer (str): Radar layer to disp
        Param zoom (int): Zoom level for the basemap
        Param show_alerts: True/False show hazard polygons
        Param warnings_list: A list of warnings
        Param hazard_list: A list of hazards
        Param frames: Number of frames

        Returns a list of PIL images.
    '''
    ########################################
    # Make and get a basemap! (and labels) #
    ########################################
    base_map, base_map_labels, map = get_basemap("coordinate",provider=base_map_layer,zoom=zoom,width=320)
    size = map.size
    minx, miny, maxx, maxy = map.extent

    print(f"\n----------------------\nNew radar images @ zoom {zoom}:\n----------------------")

    ###################################################
    # Get layer times (from WMS GetCapabilities file) #
    ###################################################
    times, times_datetime = get_times(capabilities_url)

    ##################
    # List of frames #
    ##################
    if frames == None:
        if station_mode in ["R30", "R31", "R32", "R35", "---"]: #Less frames when in clean air mode.
            num_frames = 5
        else:
            num_frames = 10
    else:
        num_frames = frames
    #Sometimes there's less times than the number of frames...
    if len(times) < num_frames:
        num_frames = len(times)
    else:
        pass

    #Make a list of frames
    prev_images =[*range(0, num_frames, 1)] #e.g. [0,1,2,3]
    prev_times = [*range(int(num_frames/-1),0, 1)] #e.g. [-1,-2,-3,-4]
    image_list = []

    #######################################
    # Go through and construct each frame #
    #######################################
    for i,image in enumerate(prev_images):

        ###########################
        # Get latest radar images #
        ###########################
        TIME = times[prev_times[i]]
        TIME_for_url = TIME.replace(':','%3A')
        bbox=f'{miny}%2C{minx}%2C{maxy}%2C{maxx}'

        radar_url = f"https://opengeo.ncep.noaa.gov:443/geoserver/{station}/ows?SERVICE=WMS&service=WMS&version=1.3.0&request=GetMap&layers={station}_{layer}&styles=&width={size[0]}&height={size[1]}&crs={SRS}&bbox={bbox}&format={format}&transparent={transparent}&bgcolor={bg_colour}&exceptions={EXCEPTION}&time={TIME_for_url}"

        try: #Try to get the radar image
            response_radar = requests.get(radar_url, headers=headers, timeout=10)
        except requests.exceptions.ConnectionError:
            print("Connection problems")
            time.sleep(5)
            continue

        if response_radar: #If we can get a radar image
            radar = Image.open(BytesIO(response_radar.content))
        else: #or if we can't
            print(f"\tCouldn't get radar image! ({response_radar})")
            continue

        # Is the radar image blank?
        extrema = radar.convert("L").getextrema() #Extrema reports the min & max colour values.
        if extrema == (255,255): #If blank
            print(f"Radar image{image}: {TIME} UTC  (blank image)")
            continue #If it's blank, skip it!
        else:
            print(f"Radar image{image}: {TIME} UTC")
            pass

        combined = base_map
        combined_width, combined_height = combined.width,combined.height

        ################
        #   Warnings   #
        ################
        if len(warnings_list) > 0:
            warning_layer = Image.new('RGBA',combined.size,(255,0,0,0))
            combined_warning_annotation = ImageDraw.Draw(warning_layer)

            #Make warning polygons & labels
            for warning in warnings_list:
                polygon = warning[2]
                polygons_pixels = []

                for points in polygon:
                    pixel_x, pixel_y = map.rev_geocode((points[0],points[1]))
                    pixel_x, pixel_y = round(pixel_x),round(pixel_y)
                    polygons_pixels.append((pixel_x, pixel_y))

                polygon = polygons_pixels

                # Distinguish between watches & warnings (Warnings are more dangerous)
                if "Warning" in warning[0]:
                    stroke_colour = (255,0,0,255)
                    font_colour = (255,0,0,255)
                    opacity = 255
                    text = "!!!"
                else:
                    stroke_colour = (255,255,0,255)
                    font_colour = (0,0,0,255)
                    opacity = 170
                    text = ""

                #Colours for different types
                if "Marine" in warning[0]:
                    fill_colour = (0,228,255,opacity)
                elif "Thunderstorm" in warning[0]:
                    fill_colour = (255,255,0,opacity)
                elif "Tornado" in warning[0]:
                    fill_colour = (196,0,0,opacity)
                else:
                    fill_colour = (255,255,255,opacity)

                #Make the polygon
                combined_warning_annotation.polygon(
                    polygon,
                    fill=fill_colour,
                    outline=stroke_colour)
                #Find the center of the polygon
                poly_center = centroid(polygon)
                #Add text to the center of the polygon
                combined_warning_annotation.text(
                    poly_center,
                    text,
                    font=fnt,
                    fill=font_colour,
                    stroke_width=5,
                    stroke_fill=(255,255,255,200)
                    )

            # Warning fill colour for a decorative ring border (see Times, Decoration)
            if "Tornado Warning" in [elem for sublist in warnings_list for elem in sublist]:
                warning_fill_colour = (255,0,0,255)
            elif "Tornado Watch" in [elem for sublist in warnings_list for elem in sublist]:
                warning_fill_colour = (255,174,0,255)
            elif "Severe Thunderstorm Warning" in [elem for sublist in warnings_list for elem in sublist]:
                warning_fill_colour = (255,255,0,255)
            elif "Severe Thunderstorm Watch" in [elem for sublist in warnings_list for elem in sublist]:
                warning_fill_colour = (255,255,0,150)
            else:
                fill_colour = (0,0,0,0)

        ######################
        #   Alerts/Hazards   #
        ######################
        if show_alerts:
            # If there's hazards, make a hazard layer
            if len(hazard_list) > 0:
                hazard_layer = Image.new('RGBA',combined.size,(255,0,0,0))
                combined_hazard = ImageDraw.Draw(hazard_layer)

                # Make hazard polygons & labels
                for hazard in hazard_list[0]:
                    hazard_type = hazard[0]
                    hazard_onset = hazard[1]    #Onset of hazard
                    polygon_hazard = hazard[2]  #Coordinates of polygon
                    hazard_ends = hazard[3]     #End/expiration of hazard
                    polygon_hazard_pixels = []

                    # Convert polygon lat,long coordinates into pixel coordinates
                    for hazard_points in polygon_hazard:
                        pix_x, pix_y = map.rev_geocode((hazard_points[0],hazard_points[1]))
                        pix_x, pix_y = round(pix_x),round(pix_y)
                        polygon_hazard_pixels.append((pix_x, pix_y))

                    polygon_hazard = polygon_hazard_pixels

                    #Styles to distinguish between watches & warnings
                    if "Warning" in hazard_type:
                        stroke_colour = (255,0,0,255) #Red
                        font_colour = (255,0,0,255)
                    else:
                        stroke_colour = (255,255,0,255) #Yellow
                        font_colour = (0,0,0,255)


                    opacity = 200

                    #Colours for different types
                    if "High" in hazard_type:
                        fill_colour = (245,212,142,opacity) #Tan/beige, #F5D48E
                    elif "Extreme" in hazard_type:
                        fill_colour = (245,212,142,opacity) #Tan/beige, #F5D48E
                    elif "Gale" in hazard_type:
                        fill_colour = (245,212,142,opacity) #Tan/beige, #F5D48E
                    elif "Hurricane" in hazard_type:
                        fill_colour = (147,255,0,opacity) #Lime green, #93FF00
                    elif "Tropical" in hazard_type:
                        fill_colour = (147,255,0,opacity) #Lime green, #93FF00
                    elif "Blizzard" in hazard_type:
                        fill_colour = (167,58,157,opacity) #Dark purple, #A73A9D
                    elif "Ice" in hazard_type:
                        fill_colour = (129,231,234,opacity) #Sky blue, #81E7EA
                    elif "Winter" in hazard_type:
                        fill_colour = (129,172,234,opacity) #Cornflower blue, #81ACEA
                    elif "Storm" in hazard_type:
                        fill_colour = (255,255,0,opacity) #Yellow
                    else:
                        fill_colour = (0,0,0,255)

                    #Make the hazard polygon
                    combined_hazard.polygon(polygon_hazard,fill=fill_colour,outline=stroke_colour)
                    pass

        ###############
        #   Marker    #
        ###############
        marker_layer = Image.new('RGBA',combined.size,(255,0,0,0))
        marker_annotation = ImageDraw.Draw(marker_layer)

        #add a marker for the map center.
        map_center_x, map_center_y = map.rev_geocode(map.center)
        x0,y0,x1,y1 = map_center_x-10, map_center_y-10, map_center_x+10, map_center_y+10
        offset = 2 #Shadow offset

        marker_annotation.ellipse(#Shadow
            [x0 + offset, y0 + offset, x1 + offset, y1 + offset],
            outline=(0,0,0,100), #Grey
            width=5
            )
        marker_annotation.ellipse(#marker
            [x0, y0, x1, y1],
            outline=(255,0,0,255), #Red
            width=5
            )

        #########################
        #   Times, decoration   #
        #########################
        annotation_layer = Image.new('RGBA',combined.size,(255,0,0,0))
        combined_annotation = ImageDraw.Draw(annotation_layer)

        combined_annotation.ellipse( #Decorative ring!
            (10,-30,310,270),
            outline=(150,150,150,255),
            width=7
            )
        # If there's a LOCAL warning, the make the ring thicker
        if len(local_warnings) > 0:
            combined_annotation.ellipse(
                (10,-30,310,270),
                outline=warning_fill_colour,
                width=15
                )

        # Date & Time
        the_time_local = convert_tz(times_datetime[prev_times[i]],'UTC',timeZone) #Convert to local timezone
        datetime_string = the_time_local.strftime("%H:%M %Z") #Make it into a string
        time_since = datetime.now(pytz.timezone(timeZone)) - the_time_local #Calculate time since using current time.
        time_since = round(time_since.seconds/60)
        if time_since < 10: #Add a filling zero if less than 10
            filler = "0"
        else:
            filler = ""
        datetime_string = f"{datetime_string} ({filler}{time_since} mins)"

        #Centre the time based on text length.
        text_length = combined_annotation.textlength(datetime_string,font=fnt_medium)
        text_pos_x = (320 - text_length)/2
        combined_annotation.text(
            (text_pos_x,0),
            datetime_string,
            font=fnt_medium,
            fill=(0,0,0,255),
            stroke_width=3,
            stroke_fill=(255,255,255,255)
            )

        # Local alerts as a label
        if len(local_alerts[0]) > 0:
            pos_y = 23
            pos_x = 0
            unique_hazards = local_alerts[1]
            for a_hazard_type in unique_hazards:
                #Distinguish between watches & warnings
                if "Warning" in a_hazard_type:
                    stroke_colour = (255,0,0,255)
                else:
                    stroke_colour = (255,255,0,255)
                    font_colour = (0,0,0,255)
                #Colours for different types
                if "High" in a_hazard_type:
                    fill_colour = (245,212,142,255) #Tan/beige, #F5D48E
                    font_fill = (0,0,0,255)
                elif "Extreme" in a_hazard_type:
                    fill_colour = (245,212,142,255) #Tan/beige, #F5D48E
                    font_fill = (0,0,0,255)
                elif "Gale" in a_hazard_type:
                    fill_colour = (245,212,142,255) #Tan/beige, #F5D48E
                    font_fill = (0,0,0,255)
                elif "Hurricane" in a_hazard_type:
                    fill_colour = (147,255,0,255) #Lime green, #93FF00
                    font_fill = (0,0,0,255)
                elif "Tropical" in a_hazard_type:
                    fill_colour = (147,255,0,255) #Lime green, #93FF00
                    font_fill = (0,0,0,255)
                elif "Blizzard" in a_hazard_type:
                    fill_colour = (167,58,157,255) #Dark purple, #A73A9D
                    font_fill = (255,255,255,255)
                elif "Ice" in a_hazard_type:
                    fill_colour = (129,231,234,255) #Sky blue, #81E7EA
                    font_fill = (255,255,255,255)
                elif "Winter" in a_hazard_type:
                    fill_colour = (129,172,234,255) #Cornflower blue, #81ACEA
                    font_fill = (255,255,255,255)
                elif "Storm" in a_hazard_type:
                    fill_colour = (255,255,0,255) #Yellow
                else:
                    fill_colour = (255,255,255,255)
                    font_fill = (0,0,0,255)

                if len(unique_hazards) >= 3:
                    alert_font = fnt_small
                    y_offset = 15
                else:
                    alert_font = fnt_medium
                    y_offset = 20

                text_length = combined_annotation.textlength(a_hazard_type,font=alert_font)
                pos_x = (320 - text_length)/2
                #Rounded start
                combined_annotation.chord(
                    (pos_x-5,pos_y, pos_x+15, pos_y+y_offset),
                    90,
                    270,
                    fill=fill_colour,
                    outline=stroke_colour,
                    width=1
                    )
                #Rectangle
                combined_annotation.rectangle(
                    (pos_x+5,pos_y,pos_x+text_length,pos_y+y_offset),
                    fill=fill_colour,
                    outline=stroke_colour,
                    width=1
                    )
                #Rounded end
                combined_annotation.chord(
                    (pos_x+text_length-10, pos_y, pos_x+text_length+10, pos_y+y_offset),
                    270,
                    90,
                    fill=fill_colour,
                    outline=stroke_colour,
                    width=1
                    )
                #Rectangle (to cover up internal strokes)
                combined_annotation.rectangle(
                    (pos_x+3,pos_y+1,pos_x+text_length+3,pos_y+y_offset-1),
                    fill=fill_colour
                    )
                #Text
                combined_annotation.text(
                    (pos_x+2,pos_y),
                    a_hazard_type,
                    font=alert_font,
                    fill=font_fill,
                    stroke_width=0,
                    stroke_fill=(255,255,255,200)
                    )
                pos_y = pos_y + y_offset + 2


        ########################################
        #   Putting all the layers together!   #
        ########################################
        if show_alerts: #Hazard layer
            if len(hazard_list) > 0:
                combined = Image.alpha_composite(combined, hazard_layer)

        # Basemap + Radar (note function to make radar image transparent)
        combined = Image.alpha_composite(combined, make_transparent(radar,155))
        if len(warnings_list) > 0: #Warning layer
            combined = Image.alpha_composite(combined, warning_layer)
        combined = Image.alpha_composite(combined, base_map_labels) #Base + map labels
        combined = Image.alpha_composite(combined, marker_layer) #Maker

        #Put all the layers together!
        combined = Image.alpha_composite(combined, annotation_layer) #Annotations
        #Circle overlay!
        circle_overlay = Image.open(f"{CURR_DIR}circle_overlay.png")
        combined = Image.alpha_composite(combined, circle_overlay)

        image_list.append(combined)
    print("Done!")

    return image_list
def get_all_alerts(*hazard_types, coordinates=None):
    ''' Get the list of active hazards & warnings in an area.
        param hazard_types: An array of hazards for the WFS cql_filter.
        param coordinates: Bounding coordinates. Can be:
                            - (x,y) tuple for a point location
                            - Geotiler map construct

        Returns a list of warnings, (hazards, unique hazards)

    '''
    global minx
    global miny
    global maxy
    global maxx
    global hazard_polygons_pixel
    global warning_polygons_pixel

    ##########################
    # Minx, miny, maxx, maxy #
    ##########################
    if type(coordinates) is tuple: #If coordinates are a (x,y) point
        minx, miny = coordinates
        maxx, maxy = coordinates
    elif type(coordinates) is geotiler.map.Map: #If coordinates are a GeoTiler map
        minx, miny, maxx, maxy = coordinates.extent
    else: #Else use WMS layer extent.
        minx, miny, maxx, maxy = minx, miny, maxx, maxy

    ##############
    # cql filter #
    ##############
    # We can show certain haxards using the WFS cql filter
    types = "+AND+("
    if len(hazard_types) > 1:
        for i, hazard in enumerate(hazard_types):
            if i == len(hazard_types)-1:
                string = f"prod_type%20LIKE%27%25{hazard}%25%27)"
            else:
                string = f"prod_type%20LIKE%27%25{hazard}%25%27+OR+"

            types = f"{types}{string}"
    elif len(hazard_types) > 0:
        types = f"{types}prod_type%20LIKE%27%25{hazard_types}%25%27)"
    else:
        types = ""

    #####################
    # Get current times #
    #####################
    hazard_time, hazard_datetime = get_times(alert_capabilities_url)
    hazard_time = hazard_time[-1] #Get just the latest time

    warning_time, warning_datetime = get_times(warnings_capabilities_url)
    warning_time = warning_time[-1] #Get just the latest time

    ##################################################
    # Construct full URL for warning & hazard layers #
    ##################################################
    hazard_json_url = f"https://opengeo.ncep.noaa.gov/geoserver/wwa/ows?service=wfs&version=2.0.0&request=GetFeature&outputFormat=application%2Fjson&typeNames=hazards&srsName=EPSG:4326&cql_filter=IDP_FileDate+%3D+{hazard_time}+AND+BBOX(geom,{minx},{miny},{maxx},{maxy},%27EPSG:4326%27){types}"

    warning_json_url = f"https://opengeo.ncep.noaa.gov/geoserver/wwa/ows?service=wfs&version=2.0.0&request=GetFeature&outputFormat=application%2Fjson&typeNames=warnings&srsName=EPSG:4326&cql_filter=IDP_FileDate+%3D+{warning_time}+AND+BBOX(geom,{minx},{miny},{maxx},{maxy},%27EPSG:4326%27)"

    #############################
    # Get warnings and hazards  #
    #############################
    try: #Warnings
        response_warning = requests.get(warning_json_url, headers=headers,timeout=5)
    except:
        print("Connection problem getting warning file.")
        response_warning = False
    try: #Hazards
        response_hazard = requests.get(hazard_json_url, headers=headers,timeout=5)
    except:
        print("Connection problem getting hazard file.")
        response_hazard = False

    warnings_list = []
    warning_polygons = []

    hazard_list = []
    hazard_polygons = []
    hazard_types_list = []
    unique_hazards = []

    if response_hazard:
        hazard_json_file = response_hazard.json()
        total_hazards = hazard_json_file['totalFeatures']

        print(f"\n--------------\nHazards: ({hazard_json_file['totalFeatures']})\n--------------")

        if total_hazards > 0:
            for index, record in enumerate(hazard_json_file['features']):
                hazard_type = record['properties']['prod_type']
                cap_id = record['properties']['cap_id']
                onset = record['properties']['onset']
                ends = record['properties']['ends']

                #Sometimes the 'ends' field is blank, so we'll use the expiration instead.
                if ends in ["",None]:
                    ends = record['properties']['expiration']

                #Convert & remake onset & end times to local radar timezone
                onset_local_datetime = convert_tz(onset,'UTC',timeZone) #Converted to local datetime
                ends_local_datetime = convert_tz(ends,'UTC',timeZone) #Converted to local datetime
                onset_local = datetime.strftime(onset_local_datetime, '%H:%M (%A %d %B)') #Remade to string
                ends_local = datetime.strftime(ends_local_datetime, '%H:%M (%A %d %B) %Z') #Remade to string

                #Collect the hazard type
                hazard_types_list.append(hazard_type)

                #Get polygon coordinates
                if record['geometry']['type'] == "MultiPolygon":
                    hazard_polygons.append(record['geometry']['coordinates'][0][0])

                    for polygon in hazard_polygons:
                        polygons_coordinates = []
                        for points in polygon:
                            polygons_coordinates.append((points[0], points[1]))

                    #Make the hazard list:
                    hazard_list.append([
                        hazard_type,
                        onset_local_datetime,
                        polygons_coordinates,
                        ends_local_datetime
                        ])

                    unique_hazards = list(set(hazard_types_list))
                    print(f"- {hazard_type},\t\t{onset_local} until {ends_local}")
                else:
                    pass

        else:
            print("- No hazards!")

    else:
        print(f"Unable to get Hazards json file ({response_hazard})")

    if response_warning:
        warning_json_file = response_warning.json()

        print(f"\n--------------\nWarnings: ({warning_json_file['totalFeatures']})\n--------------")

        if warning_json_file['totalFeatures'] > 0:
            for record in warning_json_file['features']:
                warning_type = record['properties']['prod_type']
                cap_id = record['properties']['cap_id']

                #Strip and remake the expiration time
                expiration_datetime = datetime.strptime(record['properties']['expiration'],'%Y-%m-%dT%H:%M:%S%z')
                expiration = datetime.strftime(expiration_datetime, '%Y-%m-%d, %H:%M %Z')

                # Get polygon coordinates
                if record['geometry']['type'] == "MultiPolygon":
                    warning_polygons.append(record['geometry']['coordinates'][0][0])

                    for polygon in warning_polygons:
                        polygons_coordinates = []
                        for points in polygon:
                            polygons_coordinates.append((points[0], points[1]))

                #[type, [bbox], expiration, (pixel_x,pixel_y)]
                warnings_list.append([
                    warning_type,
                    expiration,
                    polygons_coordinates
                    ])
                print(f"- {warning_type}, ends {expiration}")
        else:
            print("- No warnings!")

    else:
        print(f"Unable to get Warnings json file ({response_warning})")

    return warnings_list, (hazard_list, unique_hazards)
def make_transparent(image,transparency):
    ''' Make opague parts of a transparent image, transparent!

        Param image: The image to use.
        Param transparent: value between 0 & 255. 0 = full transparent, 255 = opaque.

        Returns a reconstructed image.
    '''
    #Make sure the image has an alpha channel
    image = image.convert("RGBA")

    #Do some array magic.
    img_array = np.array(image)
    img_array[:, :, 3] = (transparency * (img_array[:, :, :3] != 255).any(axis=2))

    return Image.fromarray(img_array)
def get_times(url):
    ''' For a layer, get a list of times by requesting the GetCapabilities XML file.
        Param url: The url for the GetCapabilities file.

        Returns a list of times (str), and a list of times (datetime)
    '''
    global times_split

    try:
        response = requests.get(url, headers=headers, timeout=10)
    except:
        print("Connection Problems: Getting times")
        response = False

    if response:
        xml_file = BytesIO(response.content)
        capabilties_dict = xmltodict.parse(xml_file.read())
        times = capabilties_dict["WMS_Capabilities"]["Capability"]["Layer"]["Layer"]["Dimension"]["#text"]
        times_datetime = []

        #The times are just a long piece of text, seperated by commas.
        #Split this up into a list!
        times = times.split(',')

        #Convert times into datetime
        for time in times:
            times_datetime.append(datetime.strptime(time,'%Y-%m-%dT%H:%M:%S.000Z'))

    else:
        times = [None,None,None,None,None,None,None,None,None,None]
        times_datetime = [None,None,None,None,None,None,None,None,None,None]
        print(f"Unable to get GetCapabilities file ({response})")

    #Return a list of times (str), and a list of times (datetime)
    return times, times_datetime
def get_basemap(mode,zoom,width,provider='stamen-toner'):
    ''' Make a basemap using GeoTiler
        Param mode: Method of getting the map extents.
        Param zoom: Zoom level
        Param width: Width of the map.
        Param provider: The map provider (see the Geotiler library for a list)

        Returns rendered basemap, rendered basemap labels, and map construct.
    '''
    global minx
    global miny
    global maxx
    global maxy
    global map_center_x
    global map_center_y
    size = (width,round(width * 0.75)) #

    if mode == "coordinate":
        # Use our lat/long (in secrets) and map size as the basis for the extent of the map.
        map = geotiler.Map( center=(lat_long[1],lat_long[0]),
                            zoom=zoom,
                            size=size,
                            provider=provider)
        map_labels = geotiler.Map(center=(lat_long[1],lat_long[0]),
                            size=size,
                            zoom=map.zoom,
                            provider='stamen-toner-labels')
        minx, miny, maxx, maxy = map.extent

    else:
        # Use the minx, miny, maxx, maxy extents from the radar layer.
        map = geotiler.Map( extent=(minx, miny, maxx, maxy),
                            zoom=zoom,
                            provider=provider)
        map_labels = geotiler.Map( extent=(minx, miny, maxx, maxy),
                            zoom=map.zoom,
                            provider='stamen-toner-labels')

    (map_center_x,map_center_y) = map.rev_geocode(map.center)
    base_map = geotiler.render_map(map)
    base_map_labels = geotiler.render_map(map_labels)

    return base_map, base_map_labels, map
def convert_tz(time,original_tz,new_tz):
    ''' Convert datetime from one timezone to another!
        Param time: (str or datetime) to convert.
        Param original_tz: Original timezone (str)
        Param new_tz: New timezone to convert to (str)

        Returns local time
    '''

    if type(time) is str:
        time = datetime.strptime(time,'%Y-%m-%dT%H:%M:%S%z')
    else:
        pass
    original_time = time.replace(tzinfo=pytz.timezone(original_tz))
    local_time = original_time.astimezone(pytz.timezone(new_tz))

    return local_time
def centroid(vertexes):
    ''' Work out centre of a polygon.
        Param vertexes

        Returns (x,y) centre
    '''
    _x_list = [vertex [0] for vertex in vertexes]
    _y_list = [vertex [1] for vertex in vertexes]
    _len = len(vertexes)
    _x = sum(_x_list) / _len
    _y = sum(_y_list) / _len
    return(_x, _y)
def play_animation(frames):
    ''' Play an animation!
        Param images: A list of images/frames.
        Param zoom: Zoom property
    '''
    global latest_image

    duration = 750
    latest_image = frames[-1]

    for frame in frames:
        start_time = time.monotonic()
        disp.image(frame)

        while time.monotonic() < (start_time + duration / 1000):
            pass
def status_images(message,background=None, background_colour=(100,100,100,200), font=fnt_goth_bold, font_colour=(255,255,255,255), xy=None, border=True):
    ''' Make an image that displays a status message.
        param message: message to display
        param background: background image.
        param background_colour: RGBA colour tuple for background box
        param font: Font to use.
        param font_colour: RGBA colour tuple
        param xy: x,y tuple.
        param border: True/False for adding circle overlay

        returns a PIL image.
    '''

    # Make an annotation layer!
    annotation_layer = Image.new('RGBA',(320,240),(120,120,120,0))
    status_annotation = ImageDraw.Draw(annotation_layer)

    # Get bounding box of the status message
    text_bbox = status_annotation.multiline_textbbox(
                                        (0,0),
                                        message,
                                        font=font,
                                        spacing=2)
    text_length = text_bbox[2]-text_bbox[0]
    text_height = text_bbox[3]-text_bbox[1]

    # If xy is given, use that... otherwise place it slightly middle left
    if xy == None:
        x_pos = 10
        y_pos = (320/2)-20
    else:
        x_pos = xy[0]
        y_pos = xy[1]

    x2_pos = text_length + 20
    y2_pos = y_pos + text_height + 8

    ##########################
    # Make the message label #
    #########################
    status_annotation.rectangle(#Text box
        (x_pos,y_pos,x2_pos,y2_pos),
        fill=background_colour,
        )
    status_annotation.chord(#Rounded end
        (x2_pos-15, y_pos, x2_pos+15, y2_pos),
        270,
        90,
        fill=background_colour
        )
    status_annotation.multiline_text(#Text
        (x_pos+15,y_pos),
        message,
        font=font,
        fill=font_colour,
        spacing=2,
        stroke_width=0
    )

    status_image = Image.new('RGBA',(320,240))
    #If a background image is given, use that
    if background is None:
        pass
    else:
        status_image = Image.alpha_composite(status_image, background)
    status_image = Image.alpha_composite(status_image, annotation_layer)
    #Add the circle overaly (if True)
    if border:
        circle_overlay = Image.open(f"{CURR_DIR}circle_overlay.png")
        status_image = Image.alpha_composite(status_image, circle_overlay)
    else:
        pass


    return status_image

disp.image(status_images("Standby!",loading))

while True:
    try:
        print("\n****************************************************")

        time_now = datetime.now(pytz.timezone(timeZone))

        print(f"\n----------------------\n     Local info:\n----------------------")
        local_warnings, local_alerts = get_all_alerts(coordinates=(lat_long[1],lat_long[0]))

        print(f"\n\n----------------------\n     Greater area:\n----------------------")
        warnings_list, hazard_list = get_all_alerts("Storm","Extreme Wind","High Wind","Gale Warning","Blizzard","Hurricane","Tropical","Winter Storm")

        ##############################
        #           Radar!           #
        ##############################
        if get_station_data(station) in ["Up","Online"]:
            radar_zoom_7 = get_radar_images(
                base_map_layer='stamen-toner',
                layer="bohp",
                zoom=7,
                show_alerts=True,
                warnings_list=warnings_list,
                hazard_list=hazard_list
                )
            if radar_zoom_7 == None:
                tech_problems = status_images("Zoom 7 problems!",loading)
                radar_zoom_7 = [tech_problems]

            #If there's warnings, check every 5 mins! (otherwise every 10)
            if len(warnings_list) > 0:
                interval = (5 * 60)
            else:
                interval = (10*60)
        else:
            # If the radar station is down, make an error image
            error_background = Image.new('RGBA',(320,240),(150,100,100,255))
            time_now = datetime.now(pytz.timezone(timeZone))

            ## Status message using current time, station, station status, and latency
            message = f'({time_now.strftime("%H:%M")}) {station} {station_status.lower()}\n Last received: {latency} mins ago'
            background_image = status_images(
                                                message,
                                                background=error_background,
                                                background_colour=(0,0,0,0),
                                                font=fnt_goth_medium,
                                                xy=(10,100),
                                                border=True
                                                )
            radar_zoom_7 = [[background_image]]

            interval = (15*60) #Check every 15 minutes

        print(f"\nChecking again in {interval/60} minutes.")
        start_time = time.monotonic()

        ##############################
        #      Displaying stuff!     #
        ##############################
        while time.monotonic() < start_time + interval:
            play_animation(radar_zoom_7)

        ### Once the waiting time has elapsed, show that were refreshing!
        time_now = datetime.now(pytz.timezone(timeZone))
        image_with_status = status_images(f'⟳ {time_now.strftime("%H:%M")}',latest_image)
        disp.image(image_with_status)

    except Exception as exception:
        ### If there's an error, get the time, and display it.
        time_now = datetime.now(pytz.timezone('America/New_York'))
        message = f'{time_now.strftime("%H:%M")}\nException: {type(exception).__name__}'
        disp.image(status_images(message,loading,font=fnt_goth_medium))
        logging.exception('Caught an error')
        break
