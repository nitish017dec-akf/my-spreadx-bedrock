"""PDF page rasterizer — converts pages to PNG images.

Uses PyMuPDF's built-in pixmap rendering, replacing the
pdfjs-dist + @napi-rs/canvas combo from the TypeScript version.

Ported from: financial-spreadx/lib/pdf/page-rasterizer.ts
"""

from __future__ import annotations

import fitz  # PyMuPDF


def rasterize_page(
    pdf_bytes: bytes, page_number: int, scale: float = 2.0
) -> bytes:
    """Rasterize a single PDF page to a PNG buffer.

    Args:
        pdf_bytes:   The full PDF file as bytes.
        page_number: 1-based page number.
        scale:       Render scale (2.0 = 2x default resolution).

    Returns:
        PNG image bytes (~150-300 KB per page at 2x scale).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[page_number - 1]  # fitz uses 0-based index
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    finally:
        doc.close()


def rotate_image_90(image_bytes: bytes) -> bytes:
    """Rotate image 90 degrees counter-clockwise. Used as a retry strategy
    when vision extraction returns 0 rows on pages with sideways content."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.rotate(90, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def rotate_image(image_bytes: bytes, angle: int) -> bytes:
    """Rotate image by exact angle (90, 180, or 270 degrees). Used for multi-angle rotation retries."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.rotate(angle, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def detect_and_correct_rotation(
    image_bytes: bytes,
    page_rect_width: float,
    page_rect_height: float,
) -> bytes:
    """Detect if rasterized content is landscape in a portrait page and rotate.

    Checks the non-white bounding box of the rasterized image against the
    page dimensions. If the page is portrait but the content is landscape
    (width > height * 1.3), rotates 90 degrees so Claude Vision sees the
    table right-side-up.

    Returns corrected PNG bytes, or original if no rotation needed.
    """
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    bbox = img.getbbox()
    if not bbox:
        return image_bytes  # Blank image — nothing to rotate

    # Only correct portrait pages — landscape pages are already rasterized correctly by PyMuPDF
    if page_rect_width >= page_rect_height:
        return image_bytes

    content_width = bbox[2] - bbox[0]
    content_height = bbox[3] - bbox[1]

    # Content aspect ratio suggests landscape table in portrait page
    if content_width > content_height * 1.3:
        img = img.rotate(90, expand=True)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    return image_bytes


def rasterize_pages(
    pdf_bytes: bytes, page_numbers: list[int], scale: float = 2.0
) -> dict[int, bytes]:
    """Rasterize multiple PDF pages to PNG buffers.

    Args:
        pdf_bytes:    The full PDF file as bytes.
        page_numbers: List of 1-based page numbers.
        scale:        Render scale.

    Returns:
        Dict mapping page number to PNG bytes.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result: dict[int, bytes] = {}
    try:
        for page_num in page_numbers:
            page = doc[page_num - 1]
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)
            result[page_num] = pix.tobytes("png")
    finally:
        doc.close()
    return result
