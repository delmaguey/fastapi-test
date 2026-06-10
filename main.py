import io
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from openai import OpenAI
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
import os

load_dotenv()
app = FastAPI()

credential = DefaultAzureCredential()
client= OpenAI(api_key=os.environ["OPENAI_API_KEY"])
storage_account = os.environ["STORAGE_ACCOUNT"]
container_name = os.environ["STORAGE_CONTAINER_NAME"]

account_url = f"https://{storage_account}.blob.core.windows.net"

credential = DefaultAzureCredential()
blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)


@app.get("/health")
def root():
    return {"message": "Service OK!"}




@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if file.content_type not in ["audio/m4a", "audio/mp3"]:
        raise HTTPException(status_code=400, detail="File type not supported. Please upload an .m4a or .mp3 file.")

    blob_name = f"{uuid.uuid4()}-{file.filename}"
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

    data = await file.read()
    blob_client.upload_blob(data, overwrite=True)

    return {
        "blob_name": blob_name,
        "url": f"{account_url}/{container_name}/{blob_name}"
    }


@app.get("/transcribe/{fname}")
def transcribe_audio(fname: str):
    if not fname.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only .mp3 files are allowed")

    try:
        blob_client = blob_service_client.get_blob_client(container="audios", blob=fname)

        buffer = io.BytesIO()
        downloader = blob_client.download_blob()
        downloader.readinto(buffer)

        buffer.seek(0)
        buffer.name = fname

        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=buffer
        )

        return {"transcript": transcript.text}

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Audio file not found")
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error: {str(ex)}")
