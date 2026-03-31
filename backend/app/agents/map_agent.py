"""Map/POI specialist agent.

References:
- D-10: MapAgent for maps, POI search, route planning
- AI-03: Autonomous tool selection based on task
"""

import json
from app.agents.base import BaseAgent, AgentResponse
from app.tools.map_tools import search_attraction, search_poi, plan_route


class MapAgent(BaseAgent):
    """Agent specializing in map and POI tasks.

    Per D-10: Handles map services, POI search, and route planning.
    """

    def __init__(self):
        super().__init__("MapAgent")
        self.tools = {
            "search_attraction": search_attraction,
            "search_poi": search_poi,
            "plan_route": plan_route
        }

    async def search_poi(
        self,
        city: str,
        keywords: str = None,
        poi_type: str = None
    ) -> dict:
        """Search for points of interest.

        Per AI-03: Select appropriate search tool based on request type.

        Args:
            city: City name
            keywords: Search keywords
            poi_type: POI type (景点, 酒店, 餐厅, etc.)

        Returns:
            POI search results
        """
        self._log_request("search_poi", city=city, keywords=keywords, poi_type=poi_type)

        try:
            # Select tool based on request type (per AI-03)
            if poi_type == "景点" or poi_type == "attractions":
                result = await self.tools["search_attraction"].ainvoke({
                    "city": city,
                    "attraction_type": "景点"
                })
            else:
                result = await self.tools["search_poi"].ainvoke({
                    "city": city,
                    "keywords": keywords or poi_type
                })

            # Parse JSON result
            poi_data = json.loads(result) if isinstance(result, str) else result

            self._log_response("search_poi", True, city=city)
            return {
                "success": True,
                "pois": poi_data
            }

        except Exception as e:
            self.logger.error(f"[MapAgent] Error: {e}")
            self._log_response("search_poi", False, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "pois": {"summary": f"暂时无法搜索{city}的地点信息"}
            }

    async def plan_route(self, origin: str, destination: str, strategy: str = None) -> dict:
        """Plan route between two locations.

        Args:
            origin: Starting point
            destination: Ending point
            strategy: Route strategy (fastest, shortest, etc.)

        Returns:
            Route planning results
        """
        self._log_request("plan_route", origin=origin, destination=destination)

        try:
            result = await self.tools["plan_route"].ainvoke({
                "origin": origin,
                "destination": destination,
                "city": ""
            })

            route_data = json.loads(result) if isinstance(result, str) else result

            self._log_response("plan_route", True)
            return {
                "success": True,
                "route": route_data
            }

        except Exception as e:
            self.logger.error(f"[MapAgent] Error: {e}")
            return {
                "success": False,
                "error": str(e),
                "route": {"summary": "暂时无法规划路线"}
            }

    async def recommend_attractions(self, city: str, interests: list = None) -> str:
        """Recommend attractions based on user interests.

        Args:
            city: City name
            interests: List of interest tags

        Returns:
            Formatted attraction recommendations
        """
        self._log_request("recommend_attractions", city=city, interests=interests)

        result = await self.search_poi(city, poi_type="景点")

        if not result["success"]:
            return f"抱歉，暂时无法推荐{city}的景点。"

        pois = result["pois"]
        return pois.get("summary", f"为您推荐{city}的景点。")
