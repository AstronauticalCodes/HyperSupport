import os
from pathlib import Path
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
import azure.cognitiveservices.speech as speechsdk

ENDPOINT = "https://24bai70356-3451-resource.services.ai.azure.com"
API_KEY = os.environ["FOUNDRY_API_KEY"]
REGION = "eastasia"


def transcribe_audio(wav_path: str) -> str:
  speech_config = speechsdk.SpeechConfig(subscription=API_KEY, region=REGION)
  audio_config = speechsdk.audio.AudioConfig(filename=wav_path)
  recognizer = speechsdk.SpeechRecognizer(
      speech_config=speech_config, audio_config=audio_config
  )
  result = recognizer.recognize_once()
  return result.text or ""


def extract_image_text(image_path: str) -> str:
  vision = ImageAnalysisClient(
      endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY)
  )
  result = vision.analyze(
      image_data=Path(image_path).read_bytes(),
      visual_features=[VisualFeatures.READ],
  )
  if not result.read or not result.read.blocks:
    return ""
  return " ".join(
      line.text for block in result.read.blocks for line in block.lines
  )


def triage_ticket(raw_text: str) -> dict:
  lang = TextAnalyticsClient(
      endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY)
  )
  pii_res = lang.recognize_pii_entities([raw_text])[0]
  sent_res = lang.analyze_sentiment([pii_res.redacted_text])[0]
  keys_res = lang.extract_key_phrases([pii_res.redacted_text])[0]

  priority = (
      "HIGH_URGENCY_ESCALATE"
      if sent_res.sentiment == "negative"
      else "STANDARD_QUEUE"
  )
  return {
      "redacted_text": pii_res.redacted_text,
      "redacted_entities": [e.category for e in pii_res.entities],
      "sentiment": sent_res.sentiment,
      "confidence": dict(sent_res.confidence_scores),
      "key_phrases": list(keys_res.key_phrases),
      "triage_decision": priority,
  }


if __name__ == "__main__":
  sample_complaint = (
      "Hi, my name is Rohan Sharma and my phone is 9876543210. "
      "My payment failed twice and my account is still locked! Fix this today."
  )
  print("--- TEXT TICKET TRIAGE ---")
  print(triage_ticket(sample_complaint))

  if Path("sample_call.wav").exists():
    spoken = transcribe_audio("sample_call.wav")
    print("\n--- AUDIO CALL TRIAGE ---")
    print("Transcript:", spoken)
    print(triage_ticket(spoken))

  if Path("sample_screenshot.png").exists():
    ocr_text = extract_image_text("sample_screenshot.png")
    print("\n--- IMAGE SCREENSHOT TRIAGE ---")
    print("OCR Text:", ocr_text)
    print(triage_ticket(ocr_text))