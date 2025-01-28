import os
from typing import Optional
from urllib.parse import quote

import requests

from arkaine.tools.tool import Argument, Example, Result, Tool


class Weather(Tool):
    """
    A tool for getting weather information for a location using OpenWeatherMap
    API.

    Args:
        api_key: OpenWeatherMap API key. If not provided, will look for
            OPENWEATHERMAP_API_KEY environment variable
        default_location: Default location to use if none provided in query
        units: Unit system to use (metric, imperial, or standard)
        formatted_str: Whether to return a formatted string or a dict.
            String format:
                Current weather in San Diego: 11°C, Few clouds
                Humidity: 72%, Wind: 3.6 km/h
            Dict format:
                {
                    'location': 'New Brunswick',
                    'temperature': 274,
                    'description': 'Clear sky',
                    'humidity': 58,
                    'wind_speed': 2.24
                }

        report_unknown_location: Whether to report an error if the location is
            not found, or just raise as an exception. Defaults to True. The
            expected output of an unknown location for each mode is:
            String format:
                Location not found
            Dict format:
                {
                    "error": "Location not found"
                }

    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_location: Optional[str] = None,
        units: str = "metric",  # metric, imperial, or standard
        formatted_str: bool = False,
        report_unknown_location: bool = True,
    ):
        self.__units = units
        self.__default_location = default_location
        self.__formatted_str = formatted_str
        self.__report_unknown_location = report_unknown_location

        if not api_key:
            api_key = os.getenv("OPENWEATHERMAP_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenWeatherMap API key must be provided either through "
                "api_key parameter or OPENWEATHERMAP_API_KEY environment variable"
            )
        self.__api_key = api_key

        args = []
        if not self.__default_location:
            args.append(
                Argument(
                    name="location",
                    description="The location to get weather for (city name, state code, "
                    "country code). For example: London,UK or New York,US",
                    type="str",
                    required=True,
                )
            )

        examples = [
            Example(
                name="weather",
                args=args,
                output=(
                    "Current weather in San Diego: 11°C, Few clouds\n"
                    "Humidity: 72%, Wind: 3.6 km/h"
                ),
                description=(
                    "Get current weather for San Diego in string format"
                ),
            ),
            Example(
                name="weather",
                args=args,
                output={
                    "location": "New Brunswick",
                    "temperature": 274,
                    "description": "Clear sky",
                    "humidity": 58,
                    "wind_speed": 2.24,
                },
                description=(
                    "Get current weather for New Brunswick in dictionary format"
                ),
            ),
        ]

        if self.__formatted_str:
            result = Result(
                type="str",
                description=(
                    "Weather information in either string format "
                    "(e.g. 'Current weather in San Diego: 11°C, Few clouds\\n"
                    "Humidity: 72%, Wind: 3.6 km/h'). If location not found,"
                    "returns 'Location not found'."
                ),
            )
        else:
            result = Result(
                type="dict",
                description=(
                    "Weather information in dictionary format containing "
                    "location, temperature, description, humidity, and "
                    "wind_speed. If location not found, returns "
                    "{'error': 'Location not found'}."
                ),
            )

        super().__init__(
            name="WeatherTool",
            description="Gets current weather information for a location",
            args=args,
            func=self.get_weather,
            examples=examples,
            result=result,
        )

    def _normalize_location(self, location: str) -> str:
        """
        Normalize location string to a consistent format: "city,state,country"
        Handles both comma-separated and space-separated formats.

        Built to handle mostly US strings as most interfaces generally don't
        include the US code.

        Args:
            location: Location string (e.g. "San Diego CA" or "New York, NY,
                US")

        Returns:
            Normalized location string (e.g. "San Diego,CA,US")
        """
        # Handle both space-separated and comma-separated formats
        location = location.replace(" ,", ",").replace(", ", ",")
        parts = []

        if "," in location:
            parts = [part.strip() for part in location.split(",")]
        else:
            # Try to split by space and identify state code
            words = location.split()
            if len(words) >= 2:
                # Check if last word is a state
                potential_state = words[-1]
                if (potential_state.lower() in states) or (
                    potential_state.upper() in states.values()
                ):
                    # Join all words except last as city name
                    parts = [" ".join(words[:-1]), potential_state]

        if len(parts) >= 2:
            city, state = parts[:2]
            country = parts[2] if len(parts) > 2 else None

            # Check if state is a US state (either full name or
            # abbreviation) and, if lacking the US code, add it.
            if (state.lower() in states) or (state.upper() in states.values()):
                state_code = states.get(state.lower(), state.upper())
                if not country:
                    return f"{city},{state_code},US"
                else:
                    return f"{city},{state_code},{country}"

        return location

    def get_weather(self, context, **kwargs) -> str:
        """
        Get current weather for the specified location.

        Returns:
            str: Formatted weather information

        Raises:
            Exception: If there's an error getting weather data
        """
        # Use provided location or default
        location = kwargs.get("location", self.__default_location)
        if not location:
            raise ValueError("No location provided and no default location set")

        location = self._normalize_location(location)

        # Build API URL
        encoded_location = quote(location)
        url = (
            f"http://api.openweathermap.org/data/2.5/weather"
            f"?q={encoded_location}&appid={self.__api_key}&units={self.__units}"
        )

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 404:
                if self.__report_unknown_location:
                    if self.__formatted_str:
                        return "Location not found"
                    else:
                        return {"error": "Location not found"}
                else:
                    raise Exception(f"Location '{location}' not found")
            response.raise_for_status()
            data = response.json()

            # Extract relevant weather information
            temp = round(data["main"]["temp"])
            description = data["weather"][0]["description"].capitalize()
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]

            # Format wind speed based on units
            if self.__units == "imperial":
                wind_unit = "mph"
            elif self.__units == "metric":
                wind_unit = "km/h"
            else:  # standard
                wind_unit = "m/s"

            # Format temperature based on units
            if self.__units == "imperial":
                temp_unit = "°F"
            elif self.__units == "metric":
                temp_unit = "°C"
            else:  # standard
                temp_unit = "K"

            # Build response string
            if self.__formatted_str:
                weather_info = (
                    f"Current weather in {data['name']}: "
                    f"{temp}{temp_unit}, {description}\n"
                    f"Humidity: {humidity}%, Wind: {wind_speed} {wind_unit}"
                )
            else:
                weather_info = {
                    "location": data["name"],
                    "temperature": temp,
                    "description": description,
                    "humidity": humidity,
                    "wind_speed": wind_speed,
                }

            return weather_info

        except requests.RequestException as e:
            raise Exception(f"Failed to get weather data: {str(e)}")
        except (KeyError, ValueError) as e:
            raise Exception(f"Error parsing weather data: {str(e)}")


states = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of Columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new Hampshire": "NH",
    "new Jersey": "NJ",
    "new Mexico": "NM",
    "new York": "NY",
    "north Carolina": "NC",
    "north Dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode Island": "RI",
    "south Carolina": "SC",
    "south Dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west Virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
