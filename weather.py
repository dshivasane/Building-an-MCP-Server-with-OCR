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
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import hashlib

# Create a server instance
server = Server("weather-server")

# Store for weather data and PDF content cache
weather_data = {}
pdf_cache = {}

# Configure allowed PDF directories (for security)
ALLOWED_PDF_DIRECTORIES = [ "C:\\Users\\Admin\\Desktop\\HOA\\pdfs"]

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
            description="Read and extract text from a local PDF file. Automatically detects scanned PDFs and uses OCR.",
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
                    },
                    "force_ocr": {
                        "type": "boolean",
                        "description": "Force OCR even if text can be extracted normally (default: false)",
                        "default": False
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

def get_pdf_hash(file_path: str) -> str:
    """Generate a hash of the PDF file for caching purposes."""
    with open(file_path, 'rb') as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    return file_hash

def get_cache_file_path(file_path: str) -> str:
    """Get the path for the cached text file."""
    pdf_dir = os.path.dirname(file_path)
    pdf_name = os.path.splitext(os.path.basename(file_path))[0]
    file_hash = get_pdf_hash(file_path)[:8]  # Use first 8 chars of hash
    cache_filename = f"{pdf_name}_ocr_{file_hash}.txt"
    return os.path.join(pdf_dir, cache_filename)

def load_cached_text(file_path: str) -> str:
    """Load cached OCR text if it exists."""
    cache_file = get_cache_file_path(file_path)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error loading cached text: {e}")
    return None

def save_cached_text(file_path: str, text: str):
    """Save OCR text to cache file."""
    cache_file = get_cache_file_path(file_path)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"OCR text cached to: {cache_file}")
    except Exception as e:
        print(f"Error saving cached text: {e}")

def extract_text_with_ocr(file_path: str, page_numbers: list[int] = None) -> str:
    """Extract text from PDF using OCR for scanned documents."""
    try:
        # Convert PDF pages to images
        if page_numbers:
            # Convert only specific pages (pdf2image uses 1-based indexing)
            first_page = min(page_numbers)
            last_page = max(page_numbers)
            images = convert_from_path(file_path, first_page=first_page, last_page=last_page)
            # Filter to only requested pages
            requested_images = []
            for i, page_num in enumerate(range(first_page, last_page + 1)):
                if page_num in page_numbers:
                    requested_images.append(images[i])
            images = requested_images
        else:
            images = convert_from_path(file_path)
        
        text_content = []
        for i, image in enumerate(images):
            try:
                # Use pytesseract to extract text from image
                page_text = pytesseract.image_to_string(image, lang='eng')
                if page_numbers:
                    actual_page = page_numbers[i] if i < len(page_numbers) else page_numbers[0] + i
                else:
                    actual_page = i + 1
                text_content.append(f"--- Page {actual_page} (OCR) ---\n{page_text}\n")
            except Exception as e:
                text_content.append(f"--- Page {actual_page} (OCR Error) ---\nError extracting text: {str(e)}\n")
        
        return "\n".join(text_content)
        
    except Exception as e:
        raise RuntimeError(f"Error performing OCR on PDF: {str(e)}")

def has_extractable_text(file_path: str, sample_pages: int = 3) -> bool:
    """Check if PDF has extractable text or if it needs OCR."""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            pages_to_check = min(sample_pages, len(pdf_reader.pages))
            
            total_text_length = 0
            for i in range(pages_to_check):
                page_text = pdf_reader.pages[i].extract_text().strip()
                total_text_length += len(page_text)
            
            # If we get very little text, it's likely a scanned PDF
            avg_text_per_page = total_text_length / pages_to_check
            return avg_text_per_page > 50  # Threshold for "has meaningful text"
            
    except Exception:
        return False
    """Check if the file path is in an allowed directory."""
    file_path = os.path.abspath(file_path)
    return any(file_path.startswith(os.path.abspath(allowed_dir)) 
              for allowed_dir in ALLOWED_PDF_DIRECTORIES)

def is_path_allowed(file_path: str) -> bool:
    """Check if the file path is in an allowed directory."""
    file_path = os.path.abspath(file_path)
    return any(file_path.startswith(os.path.abspath(allowed_dir)) 
              for allowed_dir in ALLOWED_PDF_DIRECTORIES)

def extract_pdf_text(file_path: str, page_numbers: list[int] = None, force_ocr: bool = False) -> str:
    """Extract text from PDF file, using OCR for scanned documents."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")
    
    if not is_path_allowed(file_path):
        raise PermissionError(f"Access denied to file: {file_path}")
    
    # Check for cached OCR text first (only if reading full document)
    if not page_numbers and not force_ocr:
        cached_text = load_cached_text(file_path)
        if cached_text:
            return f"[Using cached OCR text]\n\n{cached_text}"
    
    # Check cache for regular extraction
    cache_key = f"{file_path}:{page_numbers}"
    if cache_key in pdf_cache and not force_ocr:
        return pdf_cache[cache_key]
    
    try:
        # First try regular text extraction
        if not force_ocr and has_extractable_text(file_path):
            # Regular PDF with extractable text
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
        else:
            # Scanned PDF - use OCR
            print(f"Using OCR for PDF: {file_path}")
            full_text = extract_text_with_ocr(file_path, page_numbers)
            
            # Cache OCR results to file (only for full document extraction)
            if not page_numbers:
                save_cached_text(file_path, full_text)
        
        # Cache the result in memory (limit cache size for memory management)
        if len(pdf_cache) < 10:  # Simple cache limit
            pdf_cache[cache_key] = full_text
        
        return full_text
        
    except Exception as e:
        # If regular extraction fails, try OCR as fallback
        if not force_ocr:
            print(f"Regular extraction failed, trying OCR for: {file_path}")
            try:
                ocr_text = extract_text_with_ocr(file_path, page_numbers)
                if not page_numbers:
                    save_cached_text(file_path, ocr_text)
                return ocr_text
            except Exception as ocr_error:
                raise RuntimeError(f"Both regular extraction and OCR failed. Regular error: {str(e)}, OCR error: {str(ocr_error)}")
        else:
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
        force_ocr = arguments.get("force_ocr", False)
        
        if not file_path:
            raise ValueError("Missing file_path parameter")
        
        try:
            pdf_text = extract_pdf_text(file_path, page_numbers, force_ocr)
            
            # Truncate very long content
            if len(pdf_text) > 15000:
                pdf_text = pdf_text[:15000] + "\n\n[Content truncated - file is very long. Use page_numbers parameter to read specific pages]"
            
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
                    if os.path.exists(pdf_file):
                        file_size = os.path.getsize(pdf_file)
                        size_mb = file_size / (1024 * 1024)
                        
                        # Check if OCR cache exists
                        cache_file = get_cache_file_path(pdf_file)
                        cache_status = " [OCR cached]" if os.path.exists(cache_file) else ""
                        
                        # Check if it's likely a scanned PDF
                        try:
                            scan_status = " [Scanned PDF]" if not has_extractable_text(pdf_file) else " [Text PDF]"
                        except:
                            scan_status = " [Unknown type]"
                        
                        result_text += f"• {pdf_file} ({size_mb:.1f} MB){scan_status}{cache_status}\n"
                    else:
                        result_text += f"• {pdf_file} [File not accessible]\n"
            
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