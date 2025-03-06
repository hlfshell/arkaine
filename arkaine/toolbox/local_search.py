import os
from typing import List, Optional, Union

import googlemaps

from arkaine.tools.tool import Argument, Example, Result, Tool


class LocalSearch(Tool):
    """
    A tool for searching local businesses and places using Google Maps.

    This requires an API key from Google with the following APIs enabled: -
    Geocoding API - Places API - Distance Matrix API

    Args:
        api_key: Google Maps API key default_location: Optional default
            location to use if none provided

        formatted_str: Whether to return a formatted string or a dictionary

        radius_km: Default search radius in kilometers (default: 10)

        force_distance: If set, this will force the distance to be included in
            the results

        enforced_limit: If set, this will override the limit argument
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_location: Optional[str] = None,
        formatted_str: bool = False,
        radius_km: int = 10,
        force_distance: bool = False,
        enforced_limit: Optional[int] = None,
    ):
        if api_key is None:
            api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if api_key is None:
            api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key is None:
            raise ValueError(
                "No API key provided. Either provide it or set one of "
                "GOOGLE_MAPS_API_KEY or GOOGLE_API_KEY"
            )
        self.__client = googlemaps.Client(key=api_key)
        self.__default_location = default_location
        self.__force_distance = force_distance
        self.__formatted_str = formatted_str
        self.__radius_km = radius_km

        args = [
            Argument(
                name="query",
                description=(
                    "What to search for (e.g., 'coffee shops', 'parks')",
                ),
                type="str",
                required=True,
            ),
        ]

        if not self.__default_location:
            args.append(
                Argument(
                    name="location",
                    description=(
                        "The location to search in (e.g., 'Seattle, WA')"
                    ),
                    type="str",
                    required=True,
                )
            )

        self.__enforced_limit = enforced_limit
        if not enforced_limit:
            args.append(
                Argument(
                    name="limit",
                    description="Maximum number of results to return",
                    type="int",
                    required=False,
                    default=enforced_limit,
                )
            )

        if not self.__force_distance:
            args.append(
                Argument(
                    name="radius",
                    description="Search radius in kilometers",
                    type="int",
                    required=False,
                    default=radius_km,
                )
            )

        examples = [
            Example(
                name="local_search",
                args={
                    "query": "ice cream",
                    "location": "Lafayette Square, St Louis",
                    "radius": 5,
                },
                output=(
                    "Search results near Lafayette Square, St Louis:\n\n"
                    "1. Jeni's Splendid Ice Creams\n"
                    "   • Distance: 2.1 km\n"
                    "   • Address: 389 N Euclid Ave, St. Louis, MO 63108, USA\n"
                    "   • Phone: (314) 367-1700\n"
                    "   • Website: https://jenis.com/scoop-shops/jenis-central-west-end/"
                    "2. Clementine's Naughty & Nice Ice Cream\n"
                    "   • Distance: 0.3 km\n"
                    "   • Address: 1637 S 18th St, St. Louis, MO 63104, USA\n"
                    "   • Phone: (314) 474-5800\n"
                    "   • Website: https://www.clementinescreamery.com/pages/lafayette-square"
                ),
                description="Search for ice cream shops near Lafayette Square",
            ),
        ]

        if self.__formatted_str:
            result = Result(
                type="str",
                description=(
                    "A formatted string containing local search results with "
                    "business details including distance"
                ),
            )
        else:
            result = Result(
                type="dict",
                description=(
                    "A dictionary containing search results. Format: "
                    "{'results': [{'name': str, 'address': str, 'phone': str, "
                    "'url': str, 'distance_km': float}]}"
                ),
            )

        super().__init__(
            name="LocalSearch",
            description="Search for local businesses and places using maps data",
            args=args,
            func=self.search,
            examples=examples,
            result=result,
        )

    def _format_results(self, results: List[dict], location: str) -> str:
        """Format results as a human-readable string."""
        if not results:
            return "No results found."

        output = f"Search results near {location}:\n\n"

        for i, result in enumerate(results, 1):
            output += f"{i}. {result['name']}\n"
            output += f"   • Distance: {result['distance_km']} km\n"

            if result["address"]:
                output += f"   • Address: {result['address']}\n"

            if result["phone"]:
                output += f"   • Phone: {result['phone']}\n"

            if result["url"]:
                output += f"   • Website: {result['url']}\n"

            output += "\n"

        return output.strip()

    def _calculate_distance(
        self,
        origin_coords: tuple[float, float],
        destination_coords: tuple[float, float],
    ) -> float:
        """
        Calculate the driving distance between two coordinate pairs.

        Args:
            origin_coords: Tuple of (latitude, longitude) for starting point
            destination_coords: Tuple of (latitude, longitude) for destination

        Returns:
            Distance in kilometers
        """
        distance = self.__client.distance_matrix(
            origins=f"{origin_coords[0]},{origin_coords[1]}",
            destinations=f"{destination_coords[0]},{destination_coords[1]}",
            mode="driving",
        )

        # Extract distance in meters from the response
        distance_meters = distance["rows"][0]["elements"][0]["distance"][
            "value"
        ]

        # Convert to kilometers and round to 1 decimal place
        return round(distance_meters / 1000, 1)

    def _normalize_results(
        self,
        raw_results: List[dict],
        detailed_results: List[dict],
        origin_coords: tuple,
        limit: int,
    ) -> List[dict]:
        """Convert Google Places results to our standard format."""
        results = []
        for raw, detailed in zip(raw_results[:limit], detailed_results):
            # Get place coordinates
            place_lat = raw["geometry"]["location"]["lat"]
            place_lng = raw["geometry"]["location"]["lng"]

            # Calculate distance using helper method
            distance_km = self._calculate_distance(
                origin_coords, (place_lat, place_lng)
            )

            result = {
                "name": detailed["name"],
                "address": detailed.get("formatted_address", ""),
                "phone": detailed.get("formatted_phone_number", ""),
                "url": detailed.get("website", ""),
                "distance_km": distance_km,
            }
            results.append(result)
        return results

    def search(
        self,
        query: str,
        location: Optional[str] = None,
        radius: Optional[int] = None,
        limit: Optional[int] = 5,
    ) -> Union[str, dict]:
        """
        Search for local businesses and places.

        Args:
            query: What to search for
            location: Where to search (if no default set)
            radius: Search radius in kilometers
            limit: Maximum number of results to return

        Returns:
            Either a formatted string or dictionary of results
        """
        location = location or self.__default_location
        if not location:
            raise ValueError("No location provided and no default location set")

        if self.__enforced_limit:
            limit = self.__enforced_limit

        if self.__force_distance:
            radius = self.__radius_km
        else:
            radius = radius or self.__radius_km

        try:
            # First, geocode the location to get coordinates
            geocode_result = self.__client.geocode(location)
            if not geocode_result:
                raise ValueError(f"Could not find location: {location}")

            lat = geocode_result[0]["geometry"]["location"]["lat"]
            lng = geocode_result[0]["geometry"]["location"]["lng"]

            # Store the origin coordinates for distance calculation
            origin_coords = (lat, lng)

            # Perform the places search
            places_result = self.__client.places_nearby(
                location=(lat, lng),
                radius=radius * 1000,  # Convert km to meters
                keyword=query,
            )

            if not places_result.get("results"):
                if self.__formatted_str:
                    return "No results found."
                return {"results": []}

            # Get detailed information for each place
            detailed_results = []
            raw_results = places_result["results"][:limit]
            for place in raw_results:
                place_details = self.__client.place(
                    place["place_id"],
                    fields=[
                        "name",
                        "formatted_address",
                        "formatted_phone_number",
                        "website",
                    ],
                )
                if place_details.get("result"):
                    detailed_results.append(place_details["result"])

            results = self._normalize_results(
                raw_results, detailed_results, origin_coords, limit
            )

            if self.__formatted_str:
                return self._format_results(results, location)
            return {"results": results}

        except Exception as e:
            raise Exception(f"Failed to perform local search: {str(e)}")
