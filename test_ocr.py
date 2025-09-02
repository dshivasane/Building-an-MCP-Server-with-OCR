import pytesseract
from pdf2image import convert_from_path

# Test if pytesseract can find tesseract
try:
    print(f"Tesseract version: {pytesseract.get_tesseract_version()}")
    print("✓ Tesseract is working")
except:
    print("✗ Tesseract not found. Please install and add to PATH.")

# Test if pdf2image can find poppler
try:
    # This will fail if poppler is not installed
    from pdf2image.exceptions import PDFInfoNotInstalledError
    print("✓ Poppler dependencies available")
except ImportError as e:
    print(f"✗ pdf2image import error: {e}")