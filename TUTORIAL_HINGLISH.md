# SpreadX Bedrock - Hinglish Tutorial

## 📚 SpreadX Kya Hai?

SpreadX Bedrock ek powerful tool hai jo **financial PDF files se data extract karke Excel mein convert kar deta hai**. Yani agar aapke paas bank statements, accounting reports, ya kisi bhi financial document ke PDF hain, to ye tool unhe automatically process karke Excel spreadsheet mein data nikaal sakta hai.

### Kaise Kaam Karta Hai?

```
PDF File (Scanned ya Digital)
         ↓
    [Classify Pages]
         ↓
    [Filter Content]
         ↓
    [Extract Data with AI]
         ↓
    [Extract Notes]
         ↓
    Excel File (XLSX)
```

---

## 🎯 Project Ki Main Features

| Feature | Matlab |
|---------|--------|
| **PDF Processing** | Scanned PDFs aur digital PDFs dono ko handle karta hai |
| **AI-Powered Extraction** | Claude AI use karke smart data extraction |
| **Multiple Templates** | T1 se T8 tak different accounting formats support karta hai |
| **Web UI** | Streamlit se easy-to-use interface |
| **CLI Tool** | Command line se bhi use kar sakte ho |
| **Excel Export** | Formatted Excel file mein output deta hai |

---

## 🚀 Shuru Kaise Karein?

### Step 1: Installation

Pehle Python 3.11+ install karo, phir ye commands run karo:

```bash
# Project folder mein jao
cd my-spreadx-bedrock

# Requirements install karo
pip install -r requirements.txt
```

### Step 2: AWS Credentials Setup Karo

SpreadX AWS Bedrock use karta hai. Aapke paas two options hain:

**Option A: Environment Variables Set Karo**
```bash
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_REGION="us-east-1"
```

**Option B: .env File Banao**
```
# .env file banao root folder mein
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

---

## 💻 Use Kaise Karein?

### Option 1: Web Interface (Sabse Asan)

**Streamlit app use karo:**

```bash
streamlit run app.py
```

Phir browser mein `http://localhost:8501` kholo. 

**Steps:**
1. PDF file upload karo
2. Template type select karo (T1-T8 ya T0 for auto-detect)
3. DPI scale adjust karo (quality ke liye)
4. "Extract" button click karo
5. Excel file download karo

### Option 2: Command Line (CLI)

**Simple use:**
```bash
python main.py input_file.pdf
```

**Advanced use with options:**
```bash
python main.py financial_statement.pdf \
  --template T3 \
  --output result.xlsx \
  --dpi 2.0
```

**Options ki explanation:**
- `--template` : Accounting template type (T1-T8)
- `--output` : Output file name (default: auto-generated)
- `--dpi` : PDF render quality (1.0 to 3.0, jitna high utna better OCR)

---

## 📁 Project Structure Samjhiye

```
my-spreadx-bedrock/
├── app.py                 # Streamlit Web UI
├── main.py               # CLI Entry Point
├── config.py             # Configuration settings
│
├── claude/               # AI Extraction Logic
│   ├── extract.py        # Main extraction logic
│   ├── extract_notes.py  # Notes extraction
│   └── extract_vision.py # Vision model use
│
├── pdf/                  # PDF Processing
│   ├── page_classifier.py    # Pages classify karta hai
│   ├── page_filter.py        # Irrelevant pages hatata hai
│   ├── page_rasterizer.py    # PDF ko image mein convert
│   ├── scope_detector.py     # Scanned vs digital detect
│   ├── statement_classifier.py # Document type identify
│   └── column_classifier.py   # Columns classify karta hai
│
├── pipeline/             # Main Workflow
│   └── orchestrator.py   # Sabko coordinate karta hai
│
├── models/               # Data Structures
│   ├── extraction.py     # Extraction result model
│   ├── column.py         # Column metadata
│   └── page.py           # Page metadata
│
├── export/               # Output Format
│   └── xlsx_export.py    # Excel file banata hai
│
└── tests/                # Testing
    ├── unit/             # Individual components ke tests
    ├── integration/      # End-to-end tests
    └── regression/       # Regression testing
```

---

## 🔄 Pipeline Kaise Kaam Karta Hai?

### Stage 1: **Classification (Classify Karna)**
```
PDF pages ko scanner detect karta hai:
- Digital PDF? (text-based, easier to extract)
- Scanned PDF? (image-based, OCR needed)
```

### Stage 2: **Filtering (Filter Karna)**
```
Irrelevant pages hatao:
- Blank pages
- Cover pages
- Unrelated content
```

### Stage 3: **Extraction (Extract Karna)**
```
Claude AI se financial data nikalo:
- Numbers
- Column headers
- Financial metrics
```

### Stage 4: **Notes Extraction (Notes Nikalna)**
```
Important notes aur comments extract karo
```

### Stage 5: **Export (Excel Banao)**
```
Organized Excel spreadsheet mein data save karo
```

---

## 🎨 Key Components Explained

### 1. **Page Rasterizer** 
PDF ko image (PNG) mein convert karta hai taaki OCR aur vision models use kar saken.

### 2. **Column Classifier**
Ye detect karta hai ki spreadsheet mein kitne columns hain aur unka type kya hai.

### 3. **Scope Detector**
Ye pata lagata hai ki PDF scanned hai ya digital - different processing ke liye.

### 4. **Claude Extractor**
AWS Bedrock ke through Claude AI use karke smart data extraction.

### 5. **XLSX Exporter**
Final Excel file banata hai proper formatting ke saath.

---

## 📊 Template Types Samjhiye

| Template | Use Case |
|----------|----------|
| **T0_unknown** | Auto-detect (koi hint nahi dena) |
| **T1-T8** | Different accounting standards (GAAP, IFRS, etc.) |

---

## ✅ Testing Kaise Kare?

### Sabhi Tests Run Karo
```bash
pytest
```

### Sirf Unit Tests
```bash
pytest tests/unit/
```

### Sirf Integration Tests (Slow hote hain)
```bash
pytest tests/integration/ -m integration
```

### Specific Test Run Karo
```bash
pytest tests/unit/test_models.py -v
```

---

## 🛠️ Configuration Settings

`config.py` mein ye settings adjust kar sakte ho:

```python
# PDF Processing
PDF_DPI_DEFAULT = 2.0           # Default render quality
PDF_MAX_PAGES = 500             # Maximum pages process karne ke liye

# Claude Extraction
MODEL_NAME = "claude-3-5-sonnet" # AI model choice
MAX_TOKENS = 2000               # Response length limit

# Output
OUTPUT_FORMATS = ["xlsx"]       # Export format
```

---

## 🐛 Common Issues Aur Solutions

### Issue 1: "AWS Credentials Not Found"
**Solution:** 
```bash
# Check karo ke environment variables set hain
echo $AWS_ACCESS_KEY_ID

# Ya .env file mein add karo
```

### Issue 2: "OCR Quality Bahut Kharab Hai"
**Solution:**
```bash
# DPI value badhao (1.0 se 3.0 tak)
python main.py file.pdf --dpi 3.0
```

### Issue 3: "Extraction Slow Hai"
**Solution:**
```bash
# DPI kam karo performance ke liye
python main.py file.pdf --dpi 1.0

# Ya sirf important pages extract karo
```

---

## 💡 Pro Tips

1. **Template Type Jante Ho?** Correct template use karo better results ke liye
2. **Scanned PDFs?** DPI 2.5-3.0 use karo good OCR ke liye
3. **Digital PDFs?** DPI 1.0 sufficient hai, fast hoga
4. **Batch Processing?** Loop se multiple files process kar sakte ho
5. **Custom Output?** `xlsx_export.py` modify karo formatting change ke liye

---

## 📞 Debugging Tips

### Verbose Output Dekho
```bash
# Add logging flags
export DEBUG=1
python main.py file.pdf
```

### Individual Components Test Karo
```bash
# Page classifier test
from pdf.page_classifier import classify_pages
result = classify_pages("file.pdf")

# Column classifier test  
from pdf.column_classifier import classify_columns
result = classify_columns(page_image)
```

### Log Files Check Karo
```bash
# Check if logs folder hai
ls -la logs/
```

---

## 🎓 Learning Path (Agar Deep Dive Karna Ho)

1. **Start:** `app.py` ko streamlit se run karo, feel karke dekho
2. **Understand:** `main.py` read karo entry point samjhne ke liye
3. **Explore:** `pipeline/orchestrator.py` dekho kaisi pipeline run hoti hai
4. **Deep Dive:** Individual `pdf/` modules dekho
5. **Customize:** `export/xlsx_export.py` modify karo output change ke liye
6. **Advanced:** `claude/extract.py` mein prompts fine-tune karo

---

## 🚀 Next Steps

✅ Installation complete karo  
✅ CLI se ek PDF test karo  
✅ Web UI (Streamlit) try karo  
✅ Excel output ko check karo  
✅ Apne use case ke liye template select karo  
✅ Testing suite run karo confidence build karne ke liye  

---

## 📚 Additional Resources

- **AWS Bedrock Docs:** https://aws.amazon.com/bedrock/
- **Streamlit Guide:** https://docs.streamlit.io/
- **Claude API:** https://claude.ai/
- **PyPDF Tools:** Check `requirements.txt` for all dependencies

---

## ❓ Frequently Asked Questions (FAQs)

**Q: Ek baar mein kitne pages process kar sakta hoon?**  
A: `config.py` mein `PDF_MAX_PAGES` set karo. Default 500 pages.

**Q: Scanned PDF se better extraction kaise paunga?**  
A: DPI value badhao (2.5-3.0) aur correct template type use karo.

**Q: Custom format mein export kar sakta hoon?**  
A: `export/xlsx_export.py` modify karo.

**Q: Kya offline use kar sakta hoon?**  
A: Nahi, AWS Bedrock (internet) ke through kaam karta hai.

**Q: Multiple files batch processing kaise?**  
A: Python script likho jo loop mein `run_pipeline()` call kare.

---

**Happy Extracting! 🎉**

---

*Last Updated: April 2026*  
*Tutorial Language: Hinglish (Hindi in Roman Script)*
