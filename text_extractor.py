import logging
import os
from pathlib import Path
from fastapi import UploadFile, File, HTTPException
from pypdf import PdfReader
import docx
from supabase import create_client, Client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def extract_text_from_pdf(file_object) -> str:
    """Extracts text from a file-like PDF object."""
    logger.info("Extracting text from PDF document.")
    text = ""
    try:
        reader = PdfReader(file_object)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing PDF: {str(e)}")
    return text.strip()


def extract_text_from_docx(file_object) -> str:
    """Extracts text from a file-like DOCX object."""
    text = []
    try:
        doc = docx.Document(file_object)
        for paragraph in doc.paragraphs:
            if paragraph.text:
                text.append(paragraph.text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing DOCX: {str(e)}")
    return "\n".join(text).strip()


def store_in_supabase(file_name: str, file_type: str, content: str):
    """Inserts the extracted content into Supabase."""
    try:
        response = supabase.table("documents").insert({
            "file_name": file_name,
            "file_type": file_type,
            "content": content
        }).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database storage failed: {str(e)}")


async def upload_document(file: File):
    """
    Endpoint to upload a PDF or DOCX file, extract its text, 
    and save it to the Supabase database.
    """
    file_name = file.filename
    file_extension = Path(file_name).suffix.lower()
    
    if file_extension not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file extension. Only .pdf and .docx are allowed."
        )


    if file_extension == '.pdf':
        content = extract_text_from_pdf(file.file)
        content = sanitize_text(content)
        file_type = 'pdf'
    else:
        content = extract_text_from_docx(file.file)
        content = sanitize_text(content)
        file_type = 'docx'

    if not content:
        raise HTTPException(status_code=400, detail="The uploaded document contains no text.")


    db_result = store_in_supabase(file_name, file_type, content)


    return {
        "message": "File processed and stored successfully",
        "file_name": file_name,
        "database_record": db_result
    }



def sanitize_text(text):
    if not text:
        return text
    
    sanitized = text.encode("utf-8", "ignore").decode("utf-8")

    import unicodedata
    return "".join(ch for ch in sanitized if unicodedata.category(ch)[0] != "C" or ch in " \n\r\t")