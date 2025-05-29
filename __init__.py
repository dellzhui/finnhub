from aiohttp.web_request import Request
from aiohttp.web_response import Response, json_response
import datetime
from urllib.parse import unquote
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.history import get_significant_states_with_session
from homeassistant.components.recorder.util import session_scope
from homeassistant.components.recorder import get_instance
from homeassistant.util.dt import now


async def async_setup(hass, config: dict):

    # Register HTTP API views
    hass.http.register_view(FinnhubAnalyzeView(hass))
    hass.http.register_view(FinnhubHistoryView(hass))
    return True


# HTTP API View for /api/finnhub/analyze
class FinnhubAnalyzeView(HomeAssistantView):
    url = "/api/finnhub/analyze"
    name = "api:finnhub:analyze"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get(self, _request: Request) -> Response:
        try:
            entity_states = self.hass.states.async_all()
            finnhub_entities = [
                {
                    "entity_id": entity.entity_id,
                    "state": entity.state,
                    "attributes": entity.attributes,
                }
                for entity in entity_states
                if entity.entity_id.startswith("sensor.finnhub_")
            ]
            return json_response({"entities": finnhub_entities})
        except Exception as e:
            return json_response({"error": str(e)}, status=500)


# HTTP API View for /api/finnhub/history
class FinnhubHistoryView(HomeAssistantView):
    url = "/api/finnhub/history"
    name = "api:finnhub:history"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get(self, request: Request) -> Response:
        try:
            entity_id = request.query.get("entity_id")
            if not entity_id or not entity_id.startswith("sensor.finnhub_"):
                return json_response({"error": "Missing entity_id in query"}, status=400)

            entity_id = unquote(entity_id)

            try:
                days = int(request.query.get("days", "30"))
            except ValueError:
                return json_response({"error": "Invalid value for days"}, status=400)

            end_time = now()
            start_time = end_time - datetime.timedelta(days=days)

            def _fetch_history():
                with session_scope(hass=self.hass) as session:
                    return get_significant_states_with_session(
                        self.hass,
                        session,
                        start_time,
                        end_time,
                        entity_ids=[entity_id],
                        include_start_time_state=False,
                        significant_changes_only=False,
                        minimal_response=False,
                        no_attributes=False,
                        compressed_state_format=False,
                    )

            history = await self.hass.async_add_executor_job(_fetch_history)

            states = [
                {
                    "last_changed": str(state.last_changed),
                    "state": state.state,
                    "attributes": state.attributes,
                }
                for state in history.get(entity_id, [])
            ]

            return json_response({"history": states})
        except Exception as e:
            return json_response({"error": str(e)}, status=500)
