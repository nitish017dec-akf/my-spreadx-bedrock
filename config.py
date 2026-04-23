"""Shared configuration constants for the extraction pipeline."""

import os
import boto3
import logging
from botocore.config import Config

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler("spreadx_pipeline.log", encoding="utf-8"), # Save to file
        logging.StreamHandler() # Also print to terminal
    ]
)
logger = logging.getLogger("spreadx")

# AWS & S3 Bedrock configs
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
BEDROCK_DEFAULT_MODEL_ID = os.getenv("BEDROCK_DEFAULT_MODEL_ID", "global.anthropic.claude-sonnet-4-6")

def get_bedrock_client():
    # Long 15-minute timeout config to prevent crashes on dense pages
    config = Config(connect_timeout=120, read_timeout=900, retries={'max_attempts': 3})
    return boto3.client("bedrock-runtime", region_name=AWS_REGION, config=config)

# Page classification thresholds (from page-classifier.ts)
DIGITAL_WORD_THRESHOLD = 80
DIGITAL_ASCII_THRESHOLD = 0.90
HYBRID_WORD_THRESHOLD = 20

# Page filter continuation window
CONTINUATION_MAX_WINDOW = 8

# Text windows
PAGE_TEXT_WINDOW = 2000         # Chars scanned for statement-type signals
MAX_PAGE_TEXT_FOR_EXTRACT = 6000  # Truncate single-page text sent to Claude
MAX_CONCAT_TEXT_FOR_EXTRACT = 12000  # Truncate multi-page concatenated text
MAX_NOTE_TEXT = 4000            # Truncate note text sent to Claude

# Extraction max tokens
TEXT_EXTRACT_MAX_TOKENS = 8192     # Claude output ceiling for text extraction
VISION_EXTRACT_MAX_TOKENS = 8192   # Claude output ceiling for vision extraction

# Rasterization
DEFAULT_DPI_SCALE = 2.0
SCANNED_DPI_SCALE = 1.5        # Lower DPI for classification (speed)
