from src.pages_to_audio.config.settings import AppSettings
from src.pages_to_audio.domain.ports.ocr import OCRRequest
from src.pages_to_audio.ocr.providers.google_document_ai import GoogleDocumentAIProvider


def test_document_ai_normalizes_structure_symbols_confidence_and_quality() -> None:
    provider = GoogleDocumentAIProvider(
        AppSettings(APP_ENV="test"),
        project_id="project",
        location="us",
        processor_id="processor",
    )
    result = provider._normalize(
        {
            "document": {
                "text": "NÃO 12%",
                "pages": [
                    {
                        "imageQualityScores": {"qualityScore": 0.97},
                        "blocks": [
                            {
                                "layout": {
                                    "confidence": 0.92,
                                    "textAnchor": {
                                        "textSegments": [{"startIndex": 0, "endIndex": 7}]
                                    },
                                }
                            }
                        ],
                        "lines": [],
                        "tokens": [
                            {
                                "layout": {
                                    "confidence": 0.88,
                                    "textAnchor": {
                                        "textSegments": [{"startIndex": 4, "endIndex": 7}]
                                    },
                                }
                            }
                        ],
                        "tables": [{"headerRows": []}],
                        "formulas": [{"text": "x=1"}],
                    }
                ],
            }
        },
        OCRRequest(original_storage_key="frame.jpg"),
    )
    assert result.text == "NÃO 12%"
    assert result.blocks[0]["text"] == "NÃO 12%"
    assert result.tokens[0]["text"] == "12%"
    assert result.tables == [{"headerRows": []}]
    assert result.formulas == [{"text": "x=1"}]
    assert result.quality_metrics["qualityScore"] == 0.97
    assert result.confidence == 0.9
    assert result.model == "OCR_PROCESSOR"
