import os
import tempfile
from pathlib import Path
import streamlit as st
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
import azure.cognitiveservices.speech as speechsdk

ENDPOINT = "https://24bai70356-3451-resource.services.ai.azure.com"
REGION = "eastasia"

st.set_page_config(
    page_title="AI-901 Support Triage",
    page_icon="🛡️",
    layout="wide",
)


def triage_text(text: str, key: str) -> dict:
    lang = TextAnalyticsClient(endpoint=ENDPOINT, credential=AzureKeyCredential(key))
    pii = lang.recognize_pii_entities([text])[0]
    sent = lang.analyze_sentiment([pii.redacted_text])[0]
    keys = lang.extract_key_phrases([pii.redacted_text])[0]
    urgent = sent.sentiment == "negative"
    return {
        "redacted": pii.redacted_text,
        "pii_count": len(pii.entities),
        "entities": [f"{e.category}: {e.text}" for e in pii.entities],
        "sentiment": sent.sentiment.upper(),
        "scores": {
            "Positive": sent.confidence_scores.positive,
            "Neutral": sent.confidence_scores.neutral,
            "Negative": sent.confidence_scores.negative,
        },
        "keys": list(keys.key_phrases),
        "route": "ESCALATE TO AGENT" if urgent else "NORMAL QUEUE",
        "urgent": urgent,
    }


def speak_reply(text: str, key: str, voice: str) -> bytes:
    cfg = speechsdk.SpeechConfig(subscription=key, region=REGION)
    cfg.speech_synthesis_voice_name = voice
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out = tmp.name
    out_cfg = speechsdk.audio.AudioOutputConfig(filename=out)
    synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=out_cfg)
    synth.speak_text_async(text).get()
    data = Path(out).read_bytes()
    Path(out).unlink(missing_ok=True)
    return data


with st.sidebar:
    page = st.radio("Page", ["Triage Demo", "Know More"])
    api_key = st.text_input(
        "Foundry API Key",
        value=os.getenv("FOUNDRY_API_KEY", ""),
        type="password",
    )
    voice = st.selectbox(
        "Voice",
        ["en-US-JennyNeural", "en-US-GuyNeural", "hi-IN-AaravNeural"],
    )


if page == "Triage Demo":
    st.title("Support Triage Demo")
    st.caption("Project: 24bai70356-3451 • Region: eastasia")

    tab1, tab2, tab3 = st.tabs(["Text", "Image", "Audio"])

    with tab1:
        default_msg = (
            "Hi, I am Rohan Sharma (9876543210). My payment failed twice and my "
            "account is still locked. Fix this today."
        )
        msg = st.text_area("Input Text", value=default_msg, height=90)
        if st.button("Analyze Text", type="primary"):
            if not api_key:
                st.warning("Add Foundry API Key in sidebar.")
            else:
                with st.spinner("Analyzing..."):
                    st.session_state["res"] = triage_text(msg, api_key)
                    st.session_state["input_preview"] = msg
                    st.session_state.pop("audio", None)

    with tab2:
        img = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])
        if img and st.button("Analyze Image", type="primary"):
            if not api_key:
                st.warning("Add Foundry API Key in sidebar.")
            else:
                with st.spinner("Reading image..."):
                    vis = ImageAnalysisClient(
                        endpoint=ENDPOINT, credential=AzureKeyCredential(api_key)
                    )
                    vr = vis.analyze(
                        image_data=img.getvalue(),
                        visual_features=[VisualFeatures.READ],
                    )
                    text_out = (
                        " ".join(
                            line.text
                            for block in vr.read.blocks
                            for line in block.lines
                        )
                        if vr.read and vr.read.blocks
                        else ""
                    )
                    if not text_out:
                        st.warning("No text found in image.")
                    else:
                        st.session_state["res"] = triage_text(text_out, api_key)
                        st.session_state["input_preview"] = text_out
                        st.session_state.pop("audio", None)

    with tab3:
        wav = st.file_uploader("Upload WAV Audio", type=["wav"])
        if wav and st.button("Analyze Audio", type="primary"):
            if not api_key:
                st.warning("Add Foundry API Key in sidebar.")
            else:
                with st.spinner("Transcribing audio..."):
                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    ) as tmp:
                        tmp.write(wav.getvalue())
                        wpath = tmp.name
                    scfg = speechsdk.SpeechConfig(subscription=api_key, region=REGION)
                    acfg = speechsdk.audio.AudioConfig(filename=wpath)
                    rec = speechsdk.SpeechRecognizer(
                        speech_config=scfg, audio_config=acfg
                    )
                    transcript = rec.recognize_once().text or ""
                    Path(wpath).unlink(missing_ok=True)
                    if not transcript:
                        st.warning("Could not transcribe audio.")
                    else:
                        st.session_state["res"] = triage_text(transcript, api_key)
                        st.session_state["input_preview"] = transcript
                        st.session_state.pop("audio", None)

    if "res" in st.session_state:
        r = st.session_state["res"]
        st.divider()

        m1, m2, m3 = st.columns(3)
        m1.metric("Action", r["route"])
        m2.metric("Sentiment", r["sentiment"])
        m3.metric("PII Masked", r["pii_count"])

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Safe Text (PII Removed)")
            st.success(r["redacted"])
            st.caption("Topics: " + (", ".join(r["keys"]) if r["keys"] else "None"))
            if r["entities"]:
                st.caption("Detected PII: " + " | ".join(r["entities"]))

        with col_b:
            st.subheader("Sentiment Score")
            st.bar_chart(r["scores"], height=180)
            reply = (
                "Your urgent ticket has been escalated to a support agent."
                if r["urgent"]
                else "Your request has been added to the support queue."
            )
            if st.button("Play Voice Reply"):
                if not api_key:
                    st.warning("Add Foundry API Key in sidebar.")
                else:
                    with st.spinner("Generating voice..."):
                        st.session_state["audio"] = speak_reply(reply, api_key, voice)
            if "audio" in st.session_state:
                st.audio(st.session_state["audio"], format="audio/wav")

else:
    st.title("Know More — AI-901 Project Guide")
    st.caption("Microsoft Azure AI Fundamentals • Project: 24bai70356-3451")

    st.subheader("1. What This App Does")
    st.write(
        "It takes customer support input from **Text**, **Image**, or **Audio**, "
        "masks personal details, checks sentiment, routes urgent issues, and "
        "generates a spoken reply."
    )

    st.subheader("2. Pipeline Flow")
    st.code(
        "Text / Image (Vision OCR) / Audio (Speech-to-Text)\n"
        "  -> Azure Language (PII Redaction + Sentiment + Key Phrases)\n"
        "  -> Triage Rule (Negative => Escalate, Else => Normal Queue)\n"
        "  -> Azure Speech (Text-to-Speech Reply)"
    )

    st.subheader("3. AI-901 Syllabus Mapping")
    st.markdown(
        "| AI-901 Topic | Where Used in This Project |\n"
        "| :--- | :--- |\n"
        "| **Computer Vision (OCR)** | Reads text from uploaded screenshots/receipts |\n"
        "| **Speech (STT & TTS)** | Transcribes `.wav` calls and speaks replies |\n"
        "| **NLP & Text Analysis** | Detects sentiment, key phrases, and PII |\n"
        "| **Responsible AI** | Masks PII for privacy; flags negative cases for human review |"
    )
