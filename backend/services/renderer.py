import os
import cv2
import numpy as np
import fitz  # PyMuPDF
from PIL import Image
from reportlab.pdfgen import canvas
from typing import List, Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class DocumentRenderer:
    """Service to render bounding box overlays on documents for visual verification."""

    def __init__(self, dpi: int = 200):
        self.dpi = dpi

    def _get_confidence_color(self, conf: float) -> Tuple[int, int, int]:
        """BGR color based on confidence threshold: Green >= 90%, Yellow >= 75%, Red < 75%."""
        if conf >= 0.90:
            return (0, 255, 0)      # Green
        if conf >= 0.75:
            return (0, 255, 255)    # Yellow
        return (0, 0, 255)          # Red

    def _draw_overlays(self, img: np.ndarray, page_data: Dict[str, Any], overlays: List[Dict[str, Any]]) -> np.ndarray:
        """Draws bounding boxes and labels on a single page image."""
        img_h, img_w = img.shape[:2]
        p_w = page_data.get("width")
        p_h = page_data.get("height")

        # Scale from DI coordinates to raster image size
        scale_x = img_w / p_w if p_w and p_w > 0 else 1.0
        scale_y = img_h / p_h if p_h and p_h > 0 else 1.0

        for ov in overlays:
            poly = ov.get("polygon")
            if not poly or len(poly) != 8:
                continue
            
            conf = float(ov.get("confidence", 1.0))
            color = self._get_confidence_color(conf)
            
            # Convert to numpy points and scale
            pts = np.array([
                [poly[0] * scale_x, poly[1] * scale_y],
                [poly[2] * scale_x, poly[3] * scale_y],
                [poly[4] * scale_x, poly[5] * scale_y],
                [poly[6] * scale_x, poly[7] * scale_y]
            ], dtype=np.int32)

            # 1. Draw Bounding Polygon
            cv2.polylines(img, [pts], isClosed=True, color=color, thickness=2)

            # 2. Add Label (Field Name)
            label = ov.get("field", "Field")
            # Calculate label position (just above the top-left corner)
            x_min = int(pts[:, 0].min())
            y_min = int(pts[:, 1].min())
            
            # Draw semi-transparent background for label to ensure readability
            (label_w, label_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.rectangle(img, (x_min, y_min - label_h - 10), (x_min + label_w + 10, y_min), color, -1)
            cv2.putText(img, label, (x_min + 5, y_min - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)

        return img

    def render_pdf_to_annotated(self, pdf_path: str, analyze_result: Dict[str, Any], extraction_results: List[Dict[str, Any]]) -> bytes:
        """
        Processes a multi-page PDF/Scanned PDF and returns bytes of an annotated PDF.
        """
        logger.info(f"Rendering annotated PDF for {pdf_path}")
        doc = fitz.open(pdf_path)
        
        # 1. Prepare per-page overlays
        pages_data = analyze_result.get("pages", [])
        overlays_per_page = [[] for _ in range(len(pages_data))]
        
        for res in extraction_results:
            field_name = res.get("field", "Field")
            for inst in res.get("instances", []):
                p_idx = inst.get("page", 1) - 1
                if 0 <= p_idx < len(overlays_per_page):
                    overlays_per_page[p_idx].append({
                        "field": field_name,
                        "polygon": inst.get("polygon"),
                        "confidence": inst.get("confidence", 1.0)
                    })

        # 2. Rasterize, Annotate, and Collect
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        
        annotated_images = []
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert to OpenCV format (BGR)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            
            # Draw overlays for this page
            page_data = pages_data[i] if i < len(pages_data) else {}
            page_overlays = overlays_per_page[i] if i < len(overlays_per_page) else []
            annotated_img = self._draw_overlays(img_bgr, page_data, page_overlays)
            annotated_images.append(annotated_img)

        # 3. Write back to single PDF bytes
        import io
        output_buffer = io.BytesIO()
        c = canvas.Canvas(output_buffer)
        
        for idx, img_bgr in enumerate(annotated_images):
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            
            # Use temporary file format to bypass reportlab drawing limitations
            img_byte_arr = io.BytesIO()
            pil_img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            w, h = pil_img.size
            # Convert pixels to points for ReportLab (1 px = 72/DPI pt)
            w_pt, h_pt = w * 72 / self.dpi, h * 72 / self.dpi
            
            c.setPageSize((w_pt, h_pt))
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(img_byte_arr), 0, 0, width=w_pt, height=h_pt)
            c.showPage()
            
        c.save()
        pdf_bytes = output_buffer.getvalue()
        output_buffer.close()
        return pdf_bytes

    def render_image_to_annotated(self, img_content: bytes, page_data: Dict[str, Any], extraction_results: List[Dict[str, Any]]) -> bytes:
        """
        Processes a single image (PNG/JPG) and returns bytes of an annotated PDF.
        """
        logger.info("Rendering annotated PDF for single image")
        
        # Load image from bytes
        np_arr = np.frombuffer(img_content, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # Collect overlays
        overlays = []
        for res in extraction_results:
            field_name = res.get("field", "Field")
            for inst in res.get("instances", []):
                # Page 1 for images
                overlays.append({
                    "field": field_name,
                    "polygon": inst.get("polygon"),
                    "confidence": inst.get("confidence", 1.0)
                })

        # Draw
        annotated_img = self._draw_overlays(img_bgr, page_data, overlays)
        
        # Save to PDF
        import io
        output_buffer = io.BytesIO()
        c = canvas.Canvas(output_buffer)
        
        img_rgb = cv2.cvtColor(annotated_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        
        img_byte_arr = io.BytesIO()
        pil_img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        w, h = pil_img.size
        # Since images don't have a fixed DPI, we treat them as self.dpi for consistency in layout
        w_pt, h_pt = w * 72 / self.dpi, h * 72 / self.dpi
        
        c.setPageSize((w_pt, h_pt))
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(img_byte_arr), 0, 0, width=w_pt, height=h_pt)
        c.showPage()
        
        c.save()
        pdf_bytes = output_buffer.getvalue()
        output_buffer.close()
        return pdf_bytes
