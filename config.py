"""Shared configuration constants for the extraction pipeline."""

# Claude AI model used for all API calls
CLAUDE_MODEL = "claude-sonnet-4-6"

# Page classification thresholds (from page-classifier.ts)
DIGITAL_WORD_THRESHOLD = 80
DIGITAL_ASCII_THRESHOLD = 0.90
HYBRID_WORD_THRESHOLD = 20

# Page filter continuation window
CONTINUATION_MAX_WINDOW = 8

# Text windows
PAGE_TEXT_WINDOW = 2000         # Chars scanned for statement-type signals
MAX_PAGE_TEXT_FOR_EXTRACT = 6000  # Truncate page text sent to Claude
MAX_NOTE_TEXT = 4000            # Truncate note text sent to Claude

# Rasterization
DEFAULT_DPI_SCALE = 2.0
SCANNED_DPI_SCALE = 1.5        # Lower DPI for classification (speed)
