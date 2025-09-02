#!/usr/bin/env python3

import asyncio
import json
import httpx
import os
from pathlib import Path
from typing import Any, Sequence
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
import PyPDF2
import io

# Create a server instance
server = Server("weather-server")

# Store for weather data and PDF content cache
weather_data = {}
pdf_cache = {}

# Configure allowed PDF directories (for security)
ALLOWED_PDF_DIRECTORIES = ["C:\\Users\\Admin\\Desktop\\HOA\\pdfs"]

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
        types.Tool(
            name="read_pdf",
            description="Read and extract text from a local PDF file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the PDF file to read",
                    },
                    "page_numbers": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional: specific page numbers to read (1-indexed). If not provided, reads all pages.",
                    }
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="list_pdfs",
            description="List all PDF files in allowed directories",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Optional: specific directory to search in",
                    }
                },
                "required": [],
            },
        ),
        types.Tool(
            name="search_pdf_content",
            description="Search for specific text within a PDF file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the PDF file to search",
                    },
                    "search_term": {
                        "type": "string",
                        "description": "Text to search for within the PDF",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Whether the search should be case sensitive (default: false)",
                        "default": False
                    }
                },
                "required": ["file_path", "search_term"],
            },
        ),
    ]

def is_path_allowed(file_path: str) -> bool:
    """Check if the file path is in an allowed directory."""
    file_path = os.path.abspath(file_path)
    return any(file_path.startswith(os.path.abspath(allowed_dir)) 
              for allowed_dir in ALLOWED_PDF_DIRECTORIES)

def extract_pdf_text(file_path: str, page_numbers: list[int] = None) -> str:
    """Extract text from PDF file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")
    
    if not is_path_allowed(file_path):
        raise PermissionError(f"Access denied to file: {file_path}")
    
    # Check cache first
    cache_key = f"{file_path}:{page_numbers}"
    if cache_key in pdf_cache:
        return pdf_cache[cache_key]
    
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text_content = []
            
            # Determine which pages to read
            if page_numbers:
                pages_to_read = [p - 1 for p in page_numbers if 0 <= p - 1 < len(pdf_reader.pages)]
            else:
                pages_to_read = range(len(pdf_reader.pages))
            
            for page_num in pages_to_read:
                page = pdf_reader.pages[page_num]
                text_content.append(f"--- Page {page_num + 1} ---\n{page.extract_text()}\n")
            
            full_text = "\n".join(text_content)
            
            # Cache the result (limit cache size for memory management)
            if len(pdf_cache) < 10:  # Simple cache limit
                pdf_cache[cache_key] = full_text
            
            return full_text
            
    except Exception as e:
        raise RuntimeError(f"Error reading PDF: {str(e)}")

def find_pdf_files(directory: str = None) -> list[str]:
    """Find all PDF files in allowed directories."""
    pdf_files = []
    
    directories_to_search = [directory] if directory else ALLOWED_PDF_DIRECTORIES
    
    for dir_path in directories_to_search:
        if not os.path.exists(dir_path):
            continue
            
        if not is_path_allowed(dir_path):
            continue
            
        try:
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        full_path = os.path.join(root, file)
                        pdf_files.append(full_path)
        except PermissionError:
            continue
    
    return sorted(pdf_files)
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
    
    elif name == "read_pdf":
        file_path = arguments.get("file_path")
        page_numbers = arguments.get("page_numbers")
        
        if not file_path:
            raise ValueError("Missing file_path parameter")
        
        try:
            pdf_text = extract_pdf_text(file_path, page_numbers)
            
            # Truncate very long content
            if len(pdf_text) > 10000:
                pdf_text = pdf_text[:10000] + "\n\n[Content truncated - file is very long]"
            
            return [
                types.TextContent(
                    type="text",
                    text=f"Content from PDF file: {file_path}\n\n{pdf_text}"
                )
            ]
            
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error reading PDF file '{file_path}': {str(e)}"
                )
            ]
    
    elif name == "list_pdfs":
        directory = arguments.get("directory")
        
        try:
            pdf_files = find_pdf_files(directory)
            
            if not pdf_files:
                result_text = "No PDF files found in the specified directories."
            else:
                result_text = f"Found {len(pdf_files)} PDF files:\n\n"
                for pdf_file in pdf_files:
                    file_size = os.path.getsize(pdf_file) if os.path.exists(pdf_file) else 0
                    size_mb = file_size / (1024 * 1024)
                    result_text += f"• {pdf_file} ({size_mb:.1f} MB)\n"
            
            return [
                types.TextContent(
                    type="text",
                    text=result_text
                )
            ]
            
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error listing PDF files: {str(e)}"
                )
            ]
    
    elif name == "search_pdf_content":
        file_path = arguments.get("file_path")
        search_term = arguments.get("search_term")
        case_sensitive = arguments.get("case_sensitive", False)
        
        if not file_path or not search_term:
            raise ValueError("Missing file_path or search_term parameter")
        
        try:
            pdf_text = extract_pdf_text(file_path)
            
            # Perform search
            search_text = pdf_text if case_sensitive else pdf_text.lower()
            term_to_find = search_term if case_sensitive else search_term.lower()
            
            matches = []
            lines = search_text.split('\n')
            
            for i, line in enumerate(lines):
                if term_to_find in line:
                    # Get context (line before and after)
                    context_start = max(0, i - 1)
                    context_end = min(len(lines), i + 2)
                    context = lines[context_start:context_end]
                    matches.append(f"Line {i+1}: {' '.join(context)}")
            
            if matches:
                result_text = f"Found {len(matches)} matches for '{search_term}' in {file_path}:\n\n"
                result_text += "\n\n".join(matches[:10])  # Limit to first 10 matches
                if len(matches) > 10:
                    result_text += f"\n\n[Showing first 10 of {len(matches)} matches]"
            else:
                result_text = f"No matches found for '{search_term}' in {file_path}"
            
            return [
                types.TextContent(
                    type="text",
                    text=result_text
                )
            ]
            
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error searching PDF file '{file_path}': {str(e)}"
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