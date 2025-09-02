#!/usr/bin/env python3

import asyncio
import json
import httpx
from typing import Any, Sequence
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Create a server instance
server = Server("weather-server")

# Store for weather data
weather_data = {}

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="get_forecast",
            description="Get weather forecast for a city",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name to get forecast for",
                    }
                },
                "required": ["city"],
            },
        ),
        types.Tool(
            name="get_alerts",
            description="Get weather alerts for a US state",
            inputSchema={
                "type": "object", 
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "US state code (e.g. CA, NY, TX)",
                    }
                },
                "required": ["state"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """
    Handle tool execution requests.
    Each tool call includes a name and arguments.
    """
    if not arguments:
        arguments = {}

    if name == "get_forecast":
        city = arguments.get("city")
        if not city:
            raise ValueError("Missing city parameter")
        
        # Simulate weather forecast (in a real implementation, you'd call a weather API)
        forecast_data = {
            "city": city,
            "temperature": "72°F",
            "condition": "Partly cloudy",
            "humidity": "65%",
            "wind": "5 mph NW",
            "forecast": [
                {"day": "Today", "high": "75°F", "low": "60°F", "condition": "Partly cloudy"},
                {"day": "Tomorrow", "high": "78°F", "low": "62°F", "condition": "Sunny"},
                {"day": "Tuesday", "high": "73°F", "low": "58°F", "condition": "Light rain"},
            ]
        }
        
        return [
            types.TextContent(
                type="text",
                text=f"Weather forecast for {city}:\n"
                     f"Current: {forecast_data['temperature']}, {forecast_data['condition']}\n"
                     f"Humidity: {forecast_data['humidity']}, Wind: {forecast_data['wind']}\n\n"
                     f"3-Day Forecast:\n" +
                     "\n".join([f"{day['day']}: High {day['high']}, Low {day['low']}, {day['condition']}" 
                               for day in forecast_data['forecast']])
            )
        ]
    
    elif name == "get_alerts":
        state = arguments.get("state", "").upper()
        if not state:
            raise ValueError("Missing state parameter")
        
        # Simulate weather alerts (in a real implementation, you'd call NWS API)
        alerts_data = {
            "CA": ["Heat Advisory until 8 PM PDT", "Air Quality Alert"],
            "FL": ["Hurricane Watch", "Flood Advisory"],
            "TX": ["Severe Thunderstorm Warning"],
            "NY": ["Winter Storm Watch"],
        }
        
        alerts = alerts_data.get(state, [])
        if not alerts:
            alert_text = f"No active weather alerts for {state}"
        else:
            alert_text = f"Active weather alerts for {state}:\n" + "\n".join([f"• {alert}" for alert in alerts])
        
        return [
            types.TextContent(
                type="text", 
                text=alert_text
            )
        ]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

def main():
    """Main entry point for the server."""
    async def run():
        # Run the server using stdin/stdout streams
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="weather",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    asyncio.run(run())

if __name__ == "__main__":
    main()