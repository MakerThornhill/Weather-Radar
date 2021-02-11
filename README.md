# Weather Radar! 
## Example code for my Raspberry Pi powered Weather Radar viewer!

### What is it?

Merging [National Weather Service radar images](https://radar.weather.gov/), [Stamen Toner maps](http://maps.stamen.com/toner/#12/37.7706/-122.3782), and [OpenWeather data](https://openweathermap.org/), the Weather Radar! is a Raspberry Pi and Blinka powered weather radar viewer housed in a funky analog meter case I found in the shed!

You can find out more on [Hackaday!](https://hackaday.io/project/176547-weather-pi-dar)


### Methodology:

For a given latitude and longitude in the USA, the Weather Radar:

* Obtains the nearest radar station ID (using the [Weather API service](https://www.weather.gov/documentation/services-web-api#/default/get_points__point_))
* Uses the radar station ID (e.g. KJAX) to obtain metadata and times for previous radar layers.
* Generates a tiled base map using the [GeoTiler library](https://wrobell.dcmod.org/geotiler/intro.html) (using a given zoom level, map size, and map centre).
* Uses all of this information to make a WMS request and download the last 5 - 10 radar images. 
* For each time frame, combines the base map, radar image, and other layers and annotations using the [Pillow imaging library](https://pillow.readthedocs.io/en/latest/index.html).
* Displays the combined image for each time frame, to make a looping animation.
* Uses the latitude and longitude to get OpenWeather data for some extra forecasting jazz.
