from src.pages_to_audio.ai.confidence import (
    ReviewMode,
    decide_review,
    finalize_review,
    is_critical_text,
)


def test_ordinary_bands_use_point_nine_and_point_seven_five() -> None:
    assert decide_review(0.90, "texto normal").mode is ReviewMode.ACCEPT
    assert decide_review(0.89, "texto normal").mode is ReviewMode.VERIFY
    assert decide_review(0.75, "texto normal").mode is ReviewMode.VERIFY
    assert decide_review(0.74, "texto normal").mode is ReviewMode.RECOMPOSE


def test_critical_bands_are_stricter() -> None:
    assert decide_review(0.95, "NÃO se aplica").mode is ReviewMode.ACCEPT
    assert decide_review(0.94, "NÃO se aplica").mode is ReviewMode.VERIFY
    assert decide_review(0.85, "NÃO se aplica").mode is ReviewMode.VERIFY
    assert decide_review(0.84, "NÃO se aplica").mode is ReviewMode.RECOMPOSE
    assert is_critical_text("A casa permanece") is False
    assert is_critical_text("A) primeira alternativa") is True


def test_ambiguous_different_answer_impact_goes_manual() -> None:
    assert finalize_review(0.80, "texto", ambiguous=True).mode is ReviewMode.MANUAL
    assert finalize_review(0.80, "texto", ambiguous=False).mode is ReviewMode.VERIFY
    assert finalize_review(0.99, "texto", ambiguous=True).mode is ReviewMode.MANUAL
