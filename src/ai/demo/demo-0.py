import os
import base64
import json

from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Get API key
api_key = os.getenv("GOOGLE_API_KEY")
model = "gemini-3.5-flash-lite"
# model = "gemini-3.8-flash"
# model = "gemini-3.1-pro-preview"

# Create Client
client = genai.Client()

def stream_the_response():
    audio_path = "/run/media/datnguyen/FastDisk/telegram project/data/audio_2026-10-12_17-03-15.ogg"
    
    # 1. Đọc file và mã hóa sang base64 string
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    # 2. Truyền base64 string vào trường data
    stream = client.interactions.create(
        model=model,
        input=[
            {"type": "text", "text": "Extract text"},
            {
                "type": "audio",
                "data": audio_b64,
                "mime_type": "audio/ogg"
            },
        ],
        stream=True
    )

    collector = []
    for event in stream:
        if hasattr(event, "delta") and hasattr(event.delta, "text"):
            collector.append(event.delta.text)
            full_text = "".join(collector)
            print(full_text, end="\r", flush=True)
    print()  # Xuống dòng khi kết thúc

def understand_tool_trigger_condition():

    weather_tool = {
        "type": "function",
        "name": "dump_method",
        "description": "Do nothing",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city name, e.g. San Francisco",
                },
            },
            "required": ["location"],
        },
    }

    available_functions = {
        "dump_method": lambda location: {
            "location": location, #"temperature": "22", "unit": "celsius"
        },
    }

    user_input = "What is the temperature in London?"
    previous_id = None

    while True:
        interaction = client.interactions.create(
            model=model,
            input=user_input,
            tools=[weather_tool],
            previous_interaction_id=previous_id,
        )

        function_results = []
        for step in interaction.steps:
            if step.type == "function_call":
                result = available_functions[step.name](**step.arguments)
                print(f"Called {step.name}({step.arguments}) → {result}")
                function_results.append({
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "result": [{"type": "text", "text": json.dumps(result)}],
                })

        if not function_results:
            break

        user_input = function_results
        previous_id = interaction.id

    print(interaction.output_text)

def test_tool_not_called():
    # 1. Define a tool that requires specific inputs irrelevant to general Q&A
    shipping_tool = {
        "type": "function",
        "name": "calculate_shipping_cost",
        "description": "Calculates shipping costs based on weight and destination country.",
        "parameters": {
            "type": "object",
            "properties": {
                "weight_kg": {
                    "type": "number",
                    "description": "Package weight in kilograms",
                },
                "destination": {
                    "type": "string",
                    "description": "Destination country name",
                },
            },
            "required": ["weight_kg", "destination"],
        },
    }

    # 2. Provide a prompt that does not supply weight or destination information
    user_input = "What is the capital of France?"
    previous_id = None

    while True:
        interaction = client.interactions.create(
            model=model,
            input=user_input,
            tools=[shipping_tool],
            previous_interaction_id=previous_id,
        )

        function_results = []
        for step in interaction.steps:
            if step.type == "function_call":
                # This block will NOT be reached
                print(f"Tool called: {step.name}")
                function_results.append({
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "result": [{"type": "text", "text": "dummy"}],
                })

        if not function_results:
            break

        user_input = function_results
        previous_id = interaction.id

    # Output: "The capital of France is Paris."
    print("Model Output:", interaction.output_text)

if __name__ == "__main__":
    test_tool_not_called()